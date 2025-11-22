
def mainfunc(date):
    date = date.replace('.', '')
    result_d = 0
    result_s = 0
    result_p = 0

    d = int(date[0])+int(date[1])
    s = 0
    p = 0
    for i in date:
        s += int(i)
    for i in date[0:4]:
        p += int(i)

    while result_d > 9 or result_d == 0:
        if d > 9:
            result_d = int(str(d)[0])+int(str(d)[1])
        else:
            result_d = d
        if result_d > 9:
            result_d = int(str(result_d)[0]) + int(str(result_d)[1])
    while result_s > 9 or result_s == 0:
        if s > 9:
            result_s = int(str(s)[0]) + int(str(s)[1])
        else:
            result_s = s
        if result_s > 9:
            result_s = int(str(result_s)[0]) + int(str(result_s)[1])
    while result_p > 9 or result_p == 0:
        if p > 9:
            result_p = int(str(p)[0]) + int(str(p)[1])
        else:
            result_p = p
        if result_p > 9:
            result_p = int(str(result_p)[0]) + int(str(result_p)[1])
    return result_d, result_s, result_p

#print(mainfunc('09.08.1993'))
