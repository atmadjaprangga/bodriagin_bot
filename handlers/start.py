from .func import mainfunc
from dict import *
from aiogram import Dispatcher
from aiogram.types import Message, InputFile
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.dispatcher import FSMContext

class Date(StatesGroup):
    date = State()

async def startbot(message: Message, state: FSMContext):
    photo = InputFile('img/Logo.jpg')
    await message.answer_photo(photo=photo, caption = 'Привет, я электронный помощник супер эксперта и наставника Екатерины Бодрягиной, я могу сделать для тебя нумерологический разбор, приступим?')
    await message.answer('Отправьте свою дату рождения\n\nПример: 12.02.1992')
    await Date.date.set()

async def runfunc(message: Message, state: FSMContext):
    if len(message.text) == 10:
        try:
            d, s, p = mainfunc(message.text)
            if len(text_d[d]) > 4096:
                for x in range(0, len(text_d[d]), 4096):
                    await message.answer(text_d[d][x:x + 4096])
            else:
                await message.answer(text_d[d])
            if len(s_text[s]) > 4096:
                for x in range(0, len(s_text[s]), 4096):
                    await message.answer(s_text[s][x:x+4096])
            else:
                await message.answer(s_text[s])
            await message.answer(p_text[p])



        except Exception as e:
            print(e)
        await state.finish()
    else:
        await message.answer('Дата введена неверно! Попробуйте еще раз.\n\nПример: 12.02.1992')

def all_handlers(dp: Dispatcher):
    dp.register_message_handler(startbot, commands=['start'], state = '*')
    dp.register_message_handler(runfunc, state = Date.date)

