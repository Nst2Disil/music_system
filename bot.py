from enum import Enum
import os
import subprocess
import telebot
from telebot import types
import music21
import xml.etree.ElementTree as ET
from midi2audio import FluidSynth
from pydub import AudioSegment


bot = telebot.TeleBot("6988184286:AAED6rzN7QoS82gugcdAIpZrDSwNZwmytbA")
print('Bot works!')
# Переменные состояния
waiting_for_image = {}
waiting_for_tacts_number = {}
oemer_already_worked = {}

INPUT_PATH = 'oemer_input'
OUTPUT_PATH = 'oemer_results'

global oemer_process
oemer_process = None

wait_previous_recognition = 'Идёт обработка предыдущего запроса.\nПожалуйста, подождите.'


class CallbackTypes(Enum):
    oemer_all = "oemer_all"
    oemer_parts = "oemer_parts"
    another_img = "another_img"


def ask_for_img(chat_id):
    global waiting_for_image
    bot.send_message(chat_id, 'Отправьте изображение нотного листа.')
    waiting_for_image[chat_id] = True


# декоратор
@bot.message_handler(commands=['start'])
def main(message): # message - информация о пользователе и чате
    ask_for_img(message.chat.id)


@bot.message_handler(content_types=['photo'])
def get_photo(message):
    global waiting_for_image
    if message.chat.id in waiting_for_image:
        try:
            # идентификатор фотографии
            file_id = message.photo[-1].file_id
            # путь к фотографии в Tg
            tg_path = bot.get_file(file_id).file_path

            # Сохранение изображения
            downloaded_file = bot.download_file(tg_path)
            file_name = str(message.chat.id) + ".jpg"
            img_path = os.path.join(INPUT_PATH, file_name)
            with open(img_path, 'wb') as new_file:
                new_file.write(downloaded_file)

            markup = types.InlineKeyboardMarkup()
            btn1 = types.InlineKeyboardButton('Прослушать целиком', callback_data=CallbackTypes.oemer_all.value)
            btn2 = types.InlineKeyboardButton('Прослушать по частям', callback_data=CallbackTypes.oemer_parts.value)
            btn3 = types.InlineKeyboardButton('Выбрать другое изображение', callback_data=CallbackTypes.another_img.value)
            markup.row(btn1)
            markup.row(btn2)
            markup.row(btn3)
            bot.reply_to(message, 'Изображение принято!\nВыберите вариант прослушивания:', reply_markup=markup)
        finally:
            del waiting_for_image[message.chat.id]


@bot.callback_query_handler(func=lambda call: call.data == CallbackTypes.another_img.value)
def handle_btn3(callback_query):
    global oemer_process
    chat_id = callback_query.message.chat.id
    # если процесс ещё не запускался или уже завершился
    if oemer_process is None or oemer_process.poll() is not None:
        global oemer_already_worked
        if chat_id in oemer_already_worked:
            del oemer_already_worked[chat_id]
        
        ask_for_img(chat_id)

        # удаление последнего сообщения с кнопками
        last_reply_massage = callback_query.message.id
        bot.delete_message(chat_id, last_reply_massage)
    else:
        bot.send_message(chat_id, wait_previous_recognition)
        

# декоратор для обработки callback_data    
@bot.callback_query_handler(func=lambda callback: True)
def callback_message(callback):
    global oemer_process
    chat_id = callback.message.chat.id
    # если процесс ещё не запускался или уже завершился
    if oemer_process is None or oemer_process.poll() is not None:
        global oemer_already_worked

        img_path = os.path.join(INPUT_PATH, str(chat_id) + ".jpg")
        output_user_path = os.path.join(OUTPUT_PATH, str(chat_id))

        # проверка необходимости запуска OMR-решения
        if not chat_id in oemer_already_worked:
            wait_recognition_message = bot.send_message(chat_id, "Принято!\nИдёт процесс распознавания. Пожалуйста, подождите.")
            wait_recognition_message_id = wait_recognition_message.message_id

            if not os.path.exists(output_user_path):
                os.makedirs(output_user_path)
            else:
                # удаление файлов предыдущего распознавания
                file_list = os.listdir(output_user_path)
                for file_name in file_list:
                    file_path = os.path.join(output_user_path, file_name)
                    os.remove(file_path)

            oemer_process = run_oemer(img_path, output_user_path)
            oemer_already_worked[chat_id] = True
            if oemer_process.poll() is not None:
                bot.delete_message(chat_id, wait_recognition_message_id)

        # если процесс не выполняется
        if oemer_process.poll() is not None:
            # проверка наличия результата распознавания
            xml_path = os.path.join(output_user_path, str(chat_id) + ".musicxml")
            if not os.path.exists(xml_path):
                bot.send_message(chat_id=chat_id, text="К сожалению, не удалось провести распознавание для данного изображения.")
            else:
                if callback.data == CallbackTypes.oemer_all.value:
                    mp3_path = main_converter(xml_path, chat_id)

                    bot.send_message(chat_id=chat_id, text="Результат полного распознавания:")
                    bot.send_voice(chat_id, voice=open(mp3_path, 'rb'))
                
                if callback.data == CallbackTypes.oemer_parts.value:
                    global waiting_for_tacts_number
                    all_tacts_num = count_tacts(xml_path)
                    bot.send_message(chat_id=chat_id, text="Сколько тактов вы хотите услышать в одном сообщении?\nВведите число.")
                    waiting_for_tacts_number[chat_id] = True
                    # запрос числа тактов в одном файле у пользователя
                    @bot.message_handler(func=lambda message: True)
                    def handle_message(message):
                        global waiting_for_tacts_number
                        if chat_id in waiting_for_tacts_number:
                            try:
                                tacts_per_file = int(message.text)
                                if tacts_per_file > all_tacts_num:
                                    bot.send_message(callback.message.chat.id, "В данном произведении меньшее количество тактов. Введите другое число.")
                                else:
                                    del waiting_for_tacts_number[chat_id]
                                    bot.send_message(chat_id=chat_id, text="Результат распознавания по частям:")
                                    tacts_sets_dictionary = create_tacts_sets_dictionary(all_tacts_num, tacts_per_file)
                                    files_count = 0
                                    for name, tacts_set in tacts_sets_dictionary.items():
                                        files_count+=1
                                        new_path = os.path.join(output_user_path, str(chat_id) + "__" + name + ".musicxml")
                                        create_mini_musicXML(xml_path, new_path, tacts_set)

                                        new_mp3_path = main_converter(new_path, chat_id)
                                        bot.send_message(chat_id=chat_id, text=str(files_count) + "я часть:")
                                        bot.send_voice(chat_id, voice=open(new_mp3_path, 'rb'))
                            except ValueError:
                                bot.send_message(callback.message.chat.id, "Неверный ввод.")
    # если процесс распознавания запущен
    else:
        bot.send_message(chat_id, wait_previous_recognition)


def count_tacts(musicXML_path):
    tree = ET.parse(musicXML_path)
    root = tree.getroot()
    # поиск элементов measure в файле
    tacts = root.findall('.//measure')
    num_tacts = len(tacts)
    return num_tacts


def create_tacts_sets_dictionary(all_tacts_num, tacts_per_file):
    tacts_sets = {}
    current_set = []
    set_num = 1
    for i in range(1, all_tacts_num+1):
        current_set.append(str(i))
        if len(current_set) == tacts_per_file:
            tacts_sets[f"tacts_set{set_num}"] = current_set
            current_set = []
            set_num += 1
    if current_set: 
        tacts_sets[f"tacts_set{set_num}"] = current_set
    return tacts_sets


def create_mini_musicXML(musicXML_path, output_path, tacts_set):
    tree = ET.parse(musicXML_path)
    root = tree.getroot()
    tacts = [tact for tact in root.findall(".//measure") if tact.attrib.get('number') in tacts_set]

    # элемент part-list
    part_list = root.find(".//part-list")
    # первый элемент attributes с информацией о ключе, ключевых знаках и темпе
    attributes = root.find('.//attributes')

    # создание нового корневого элемента
    new_root = ET.Element("score-partwise")
    new_root.append(part_list)

    # создание элемента part
    part = ET.SubElement(new_root, "part")
    part.set("id", "P1")
    for tact in tacts:
        part.append(tact)

    # добавление элемента attributes в элемент первого такта
    first_tact = new_root.find(".//measure")
    first_tact.insert(0, attributes)

    # создание нового дерева XML
    new_tree = ET.ElementTree(new_root)
    new_tree.write(output_path, encoding="UTF-8", xml_declaration=True)


def main_converter(xml_path, chat_id):
    # Конвертация MusicXML в MIDI
    score = music21.converter.parse(xml_path)
    file_name, _ = os.path.splitext(xml_path)
    midiPath = file_name + ".mid"
    score.write('midi', midiPath)

    # Конвертация MIDI в аудиоформат
    wavPath = file_name + ".wav"
    mp3Path = file_name + ".mp3"
    convert_midi_to_mp3(midiPath, wavPath, mp3Path)

    return mp3Path


def convert_midi_to_mp3(midiPath, wavPath, mp3Path):
    soundFont = "GeneralUser_GS_1.471\\GeneralUser_GS_v1.471.sf2"
    fs = FluidSynth(soundFont)
    fs.midi_to_audio(midiPath, wavPath)

    audio = AudioSegment.from_wav(wavPath)
    audio.export(mp3Path, format="mp3")    


def run_oemer(img_path, output_path):
    global oemer_process
    command = f"oemer -o {output_path} {img_path}"
    oemer_process = subprocess.Popen(command, shell=True)
    stdout, stderr = oemer_process.communicate()
    return oemer_process


bot.polling(non_stop=True)
