import os
import json
import logging
from datetime import datetime, date, timedelta, timezone
from typing import Optional, Tuple, Dict

logger = logging.getLogger(__name__)

# External libs (optional). Import errors handled below.
try:
    from timezonefinder import TimezoneFinder
    from geopy.geocoders import Nominatim
except Exception:
    TimezoneFinder = None
    Nominatim = None

# Skyfield imports (preferred high-precision path)
try:
    from skyfield.api import load, Topos
    from skyfield import almanac
except Exception:
    load = None
    Topos = None
    almanac = None

# Fallback: astral (lower dependency, but less exact than Skyfield+JPL)
try:
    from astral import Observer as AstralObserver
    from astral.sun import sun as astral_sun
except Exception:
    AstralObserver = None
    astral_sun = None

# zoneinfo (Python 3.9+), fallback to backports for older interpreters
try:
    from zoneinfo import ZoneInfo
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo
    except Exception:
        ZoneInfo = None

# Simple on-disk cache for geocoding results to avoid hammering Nominatim
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "geocode_cache.json")
CACHE_PATH = os.path.abspath(CACHE_PATH)


def _load_cache() -> Dict[str, Dict]:
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.debug("Failed to read geocode cache: %s", e)
    return {}


def _save_cache(cache: Dict[str, Dict]):
    try:
        d = os.path.dirname(CACHE_PATH)
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("Failed to write geocode cache: %s", e)


# Global small instances (lazy)
_tf_instance = TimezoneFinder() if TimezoneFinder is not None else None
_geolocator_instance = Nominatim(user_agent="bodriagin_bot") if Nominatim is not None else None


def geocode_city(city: str, use_cache: bool = True) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """
    Return (lat, lon, display_name) for the given city string.
    Uses geocode_cache.json for caching results.
    """
    if not city or city.strip().lower() in ("неизвестно", "unknown", "n/a"):
        return None, None, None

    key = city.strip().lower()
    cache = _load_cache()
    if use_cache and key in cache:
        rec = cache[key]
        logger.debug("Geocode cache hit for %s -> %s", city, rec)
        return rec.get("lat"), rec.get("lon"), rec.get("display_name")

    if _geolocator_instance is None:
        logger.debug("geopy not available; cannot geocode")
        return None, None, None

    try:
        loc = _geolocator_instance.geocode(city, timeout=10)
        if not loc:
            logger.debug("geocode returned None for %s", city)
            return None, None, None
        rec = {"lat": loc.latitude, "lon": loc.longitude, "display_name": getattr(loc, "address", str(loc))}
        cache[key] = rec
        try:
            _save_cache(cache)
        except Exception:
            pass
        logger.debug("Geocoded %s -> %s", city, rec)
        return rec["lat"], rec["lon"], rec["display_name"]
    except Exception as e:
        logger.exception("Error geocoding %s: %s", city, e)
        return None, None, None


def tz_from_coords(lat: float, lon: float) -> Optional[str]:
    """
    Return IANA timezone name for coordinates using timezonefinder.
    """
    if _tf_instance is None:
        logger.debug("timezonefinder not available")
        return None
    try:
        tzname = _tf_instance.timezone_at(lat=lat, lng=lon)
        if tzname is None:
            tzname = _tf_instance.closest_timezone_at(lat=lat, lng=lon)
        return tzname
    except Exception as e:
        logger.exception("Error finding timezone for %s,%s: %s", lat, lon, e)
        return None


def _local_midnight_range_utc(local_date: date, tzname: str) -> Tuple[datetime, datetime]:
    """
    Return UTC datetimes covering the local calendar date [00:00, 24:00) for given tz.
    """
    if ZoneInfo is None:
        # fallback: assume local_date in UTC (not ideal)
        start_local = datetime(local_date.year, local_date.month, local_date.day, 0, 0, tzinfo=timezone.utc)
        end_local = start_local + timedelta(days=1)
        return start_local, end_local
    tz = ZoneInfo(tzname)
    start_local = datetime(local_date.year, local_date.month, local_date.day, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)
    return start_utc, end_utc


def compute_dawn_skyfield(lat: float, lon: float, local_date: date, tzname: str,
                          eph_path: Optional[str] = None) -> Optional[datetime]:
    """
    High-precision calculation of civil dawn (sun center at -6 degrees) using Skyfield + JPL ephemeris.
    Defensive implementation compatible with several Skyfield versions.
    Returns localized datetime (tz-aware, tzname) or None if not found.
    eph_path: optional path to local .bsp file (e.g. 'de440s.bsp'). If None, skyfield will download default.
    """
    if load is None or Topos is None or almanac is None:
        logger.debug("Skyfield not available")
        return None

    try:
        # load ephemeris (may download on first run)
        eph = load(eph_path) if eph_path else load('de440s.bsp')
        ts = load.timescale()
    except Exception as e:
        logger.exception("Failed to load ephemeris: %s", e)
        return None

    try:
        # NOTE: almanac.risings_and_settings expects a Topos-like object (not eph['earth']+Topos).
        topos = Topos(latitude_degrees=lat, longitude_degrees=lon)

        # build UTC interval that corresponds to the local_date in tzname
        start_utc_dt, end_utc_dt = _local_midnight_range_utc(local_date, tzname)

        # convert to skyfield times
        t0 = ts.utc(start_utc_dt.year, start_utc_dt.month, start_utc_dt.day,
                    start_utc_dt.hour, start_utc_dt.minute, start_utc_dt.second)
        t1 = ts.utc(end_utc_dt.year, end_utc_dt.month, end_utc_dt.day,
                    end_utc_dt.hour, end_utc_dt.minute, end_utc_dt.second)

        # First attempt: risings_and_settings with kwarg altitude_degrees
        try:
            f = almanac.risings_and_settings(eph, eph['sun'], topos, altitude_degrees=-6.0)
            times, events = almanac.find_discrete(t0, t1, f)
            for t, ev in zip(times, events):
                if int(ev) == 1:  # rising
                    dawn_utc = t.utc_datetime().replace(tzinfo=timezone.utc)
                    dawn_local = dawn_utc.astimezone(ZoneInfo(tzname)) if ZoneInfo is not None else dawn_utc
                    return dawn_local
        except TypeError:
            # try positional altitude argument (some Skyfield versions accept it positionally)
            try:
                f = almanac.risings_and_settings(eph, eph['sun'], topos, -6.0)
                times, events = almanac.find_discrete(t0, t1, f)
                for t, ev in zip(times, events):
                    if int(ev) == 1:
                        dawn_utc = t.utc_datetime().replace(tzinfo=timezone.utc)
                        dawn_local = dawn_utc.astimezone(ZoneInfo(tzname)) if ZoneInfo is not None else dawn_utc
                        return dawn_local
            except TypeError:
                # Fallback: use dark_twilight_day if available and look for transition into civil state
                try:
                    f2 = almanac.dark_twilight_day(eph, eph['sun'], topos)
                except TypeError:
                    try:
                        f2 = almanac.dark_twilight_day(eph, eph['sun'])
                    except Exception:
                        raise

                times2, events2 = almanac.find_discrete(t0, t1, f2)
                prev_state = None
                for t, ev in zip(times2, events2):
                    cur_state = int(ev)
                    if prev_state is None:
                        prev_state = cur_state
                        continue
                    # detect transition into civil twilight (common code 3)
                    if cur_state == 3 and prev_state != 3:
                        dawn_utc = t.utc_datetime().replace(tzinfo=timezone.utc)
                        dawn_local = dawn_utc.astimezone(ZoneInfo(tzname)) if ZoneInfo is not None else dawn_utc
                        return dawn_local
                    prev_state = cur_state

        # If not found in daily interval, expand +/-1 day to catch edge cases
        t0b = ts.utc((start_utc_dt - timedelta(days=1)).year, (start_utc_dt - timedelta(days=1)).month, (start_utc_dt - timedelta(days=1)).day, 0, 0, 0)
        t1b = ts.utc((end_utc_dt + timedelta(days=1)).year, (end_utc_dt + timedelta(days=1)).month, (end_utc_dt + timedelta(days=1)).day, 0, 0, 0)

        # try risings_and_settings on expanded interval
        try:
            f = almanac.risings_and_settings(eph, eph['sun'], topos, altitude_degrees=-6.0)
            timesb, eventsb = almanac.find_discrete(t0b, t1b, f)
            for t, ev in zip(timesb, eventsb):
                if int(ev) == 1:
                    dawn_utc = t.utc_datetime().replace(tzinfo=timezone.utc)
                    dawn_local = dawn_utc.astimezone(ZoneInfo(tzname)) if ZoneInfo is not None else dawn_utc
                    return dawn_local
        except Exception:
            pass

        # try dark_twilight_day on expanded interval
        try:
            try:
                f2 = almanac.dark_twilight_day(eph, eph['sun'], topos)
            except TypeError:
                f2 = almanac.dark_twilight_day(eph, eph['sun'])
            times2b, events2b = almanac.find_discrete(t0b, t1b, f2)
            prev_state = None
            for t, ev in zip(times2b, events2b):
                cur_state = int(ev)
                if prev_state is None:
                    prev_state = cur_state
                    continue
                if cur_state == 3 and prev_state != 3:
                    dawn_utc = t.utc_datetime().replace(tzinfo=timezone.utc)
                    dawn_local = dawn_utc.astimezone(ZoneInfo(tzname)) if ZoneInfo is not None else dawn_utc
                    return dawn_local
                prev_state = cur_state
        except Exception:
            logger.debug("Skyfield twilight search did not find civil dawn in expanded interval.")
            return None

        return None

    except Exception as e:
        logger.exception("Skyfield dawn calculation failed: %s", e)
        return None


def compute_dawn_astral(lat: float, lon: float, local_date: date, tzname: str) -> Optional[datetime]:
    """
    Fallback calculation using astral (less precise than Skyfield but easier to install).
    Returns localized datetime or None.
    """
    if AstralObserver is None or astral_sun is None:
        logger.debug("Astral not available")
        return None
    try:
        obs = AstralObserver(latitude=lat, longitude=lon, elevation=0)
        tz = ZoneInfo(tzname) if ZoneInfo is not None else timezone.utc
        s = astral_sun(observer=obs, date=local_date, tzinfo=tz)
        # astral returns keys like 'dawn' (civil), 'sunrise' etc.
        dawn = s.get("dawn")
        return dawn
    except Exception as e:
        logger.exception("Astral dawn calculation failed: %s", e)
        return None


def compute_civil_dawn(lat: float, lon: float, local_date: date, tzname: str,
                       prefer_skyfield: bool = True, eph_path: Optional[str] = None) -> Optional[datetime]:
    """
    Unified function: try Skyfield (high precision) first (if available), fallback to astral.
    Returns localized datetime (tz-aware) or None.
    """
    if prefer_skyfield and load is not None:
        dawn = compute_dawn_skyfield(lat, lon, local_date, tzname, eph_path=eph_path)
        if dawn is not None:
            return dawn
        # If skyfield available but failed, try astral
    # Fallback to astral if skyfield not available or failed
    return compute_dawn_astral(lat, lon, local_date, tzname)


def was_civil_dawn_before(birth_local_dt: datetime, lat: float, lon: float, tzname: str,
                          prefer_skyfield: bool = True, eph_path: Optional[str] = None) -> Tuple[Optional[bool], Optional[datetime]]:
    """
    Compute whether civil dawn had already occurred by birth_local_dt.
    birth_local_dt must be timezone-aware (tzinfo) or tzname provided to localize.
    Returns (was_dawn, dawn_local_dt) where was_dawn is True/False/None (None = unknown),
    dawn_local_dt is the localized dawn datetime or None.
    """
    try:
        if birth_local_dt.tzinfo is None:
            if ZoneInfo is None:
                logger.debug("No ZoneInfo to localize birth time")
                return None, None
            birth_local_dt = birth_local_dt.replace(tzinfo=ZoneInfo(tzname))
    except Exception:
        pass

    dawn = compute_civil_dawn(lat, lon, birth_local_dt.date(), tzname, prefer_skyfield=prefer_skyfield, eph_path=eph_path)
    if dawn is None:
        return None, None
    try:
        return (birth_local_dt >= dawn), dawn
    except Exception:
        return None, dawn


# Example short helper for combined workflow
def check_birth_city_dawn(birth_date_str: str, birth_time_str: str, city: str,
                          prefer_skyfield: bool = True, eph_path: Optional[str] = None) -> Dict:
    """
    High-level helper:
      birth_date_str: "DD.MM.YYYY"
      birth_time_str: "HH:MM"
      city: free text
    Returns dict with keys:
      lat, lon, tzname, birth_dt_local, dawn_local, was_dawn, error (if any)
    """
    out = {"city": city}
    try:
        d, m, y = map(int, birth_date_str.split("."))
        hh, mm = map(int, birth_time_str.split(":"))
    except Exception as e:
        return {"error": f"Invalid date/time format: {e}"}

    lat, lon, display = geocode_city(city)
    out.update({"lat": lat, "lon": lon, "display_name": display})
    if lat is None or lon is None:
        out["error"] = "geocode_failed"
        return out

    tzname = tz_from_coords(lat, lon)
    out["tz"] = tzname
    if not tzname:
        out["error"] = "tz_not_found"
        return out

    if ZoneInfo is not None:
        birth_local = datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(tzname))
    else:
        birth_local = datetime(y, m, d, hh, mm)
    out["birth_dt"] = birth_local.isoformat() if isinstance(birth_local, datetime) else str(birth_local)

    dawn_local = compute_civil_dawn(lat, lon, date(y, m, d), tzname, prefer_skyfield=prefer_skyfield, eph_path=eph_path)
    out["dawn_dt"] = dawn_local.isoformat() if dawn_local else None
    if dawn_local:
        out["was_dawn"] = birth_local >= dawn_local
    else:
        out["was_dawn"] = None
    return out