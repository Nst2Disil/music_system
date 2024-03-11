from multiprocessing import context
import os
import subprocess
from turtle import update
# import uuid
import telebot
from telebot import types
import music21
from telegram import Voice
# import miditime
# import pygame
# import audiosegment
# import pydub
#from pydub import AudioSegment
from midi2audio import FluidSynth
from pydub import AudioSegment


bot = telebot.TeleBot("6988184286:AAED6rzN7QoS82gugcdAIpZrDSwNZwmytbA") # для взаимодейтсвия с ботом
print('Bot works!')

# декоратор
@bot.message_handler(commands=['start'])
def main(message): # message - информация о пользователе и чате
    bot.send_message(message.chat.id, 'Отправьте изображение нотного листа (фотографию или pdf-файл).')


@bot.message_handler(content_types=['photo'])
def get_photo(message):
    # идентификатор фотографии
    file_id = message.photo[-1].file_id
    # путь к фотографии в Tg
    tg_path = bot.get_file(file_id).file_path

    # Сохранение изображения
    downloaded_file = bot.download_file(tg_path)
    file_name = str(message.chat.id) + ".jpg"
    img_path = os.path.join('oemer_input', file_name)
    with open(img_path, 'wb') as new_file:
        new_file.write(downloaded_file)

    markup = types.InlineKeyboardMarkup()
    btn1 = types.InlineKeyboardButton('Прослушать целиком', callback_data='oemer_all')
    btn2 = types.InlineKeyboardButton('Прослушать по частям', callback_data='oemer_parts')
    markup.row(btn1, btn2)
    bot.reply_to(message, 'Изображение обрабатывается!\nВыберите вариант прослушивания:', reply_markup=markup)


# декоратор для обработки callback_data    
@bot.callback_query_handler(func=lambda callback: True)
def callback_message(callback):
    chat_id = callback.message.chat.id
    bot.send_message(chat_id, "Принято!\nИдёт процесс распознавания. Пожалуйста, подождите.")
    if callback.data == 'oemer_all':
        img_path = os.path.join('oemer_input', str(chat_id) + ".jpg")
        output_path = 'oemer_results'
        run_oemer(img_path, output_path)

        # Загрузка MusicXML файла
        xml_path = os.path.join('oemer_results', str(chat_id) + ".musicxml")
        score = music21.converter.parse(xml_path)
        
        # Конвертация MusicXML в MIDI
        midi_path = os.path.join('oemer_results', str(chat_id) + ".mid")
        score.write('midi', midi_path) 

        # Отправка файла
        bot.send_message(chat_id=chat_id, text="Результат:")
        bot.send_document(chat_id=chat_id, document=open(midi_path, 'rb'))

        # Конвертация MIDI в WAV
        wav_path = os.path.join('oemer_results', str(chat_id) + ".wav")
        mp3_path = os.path.join('oemer_results', str(chat_id) + ".mp3")
        FluidSynth().midi_to_audio(midi_path, wav_path)
        sound = AudioSegment.from_wav(wav_path) 
        sound.export(mp3_path, format="mp3")
        bot.send_voice(chat_id, mp3_path)

        # Открываем MP3 файл для чтения в бинарном режиме
        # with open("C:\\Users\\nasty\Downloads\\file_example_MP3_700KB.mp3", 'rb') as audio_file:
        #     bot.send_audio(chat_id=chat_id, audio=audio_file, title="Название аудиофайла", performer="Исполнитель")
        



def run_oemer(img_path, output_path):
    command = f"oemer -o {output_path} {img_path}"
    subprocess.run(command, shell=True)


bot.polling(non_stop=True)