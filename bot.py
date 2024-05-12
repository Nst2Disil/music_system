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
waiting_for_img = False
waiting_for_number = False


def ask_for_img(chat_id):
    global waiting_for_img
    bot.send_message(chat_id, 'Отправьте изображение нотного листа.')
    waiting_for_img = True


# декоратор
@bot.message_handler(commands=['start'])
def main(message): # message - информация о пользователе и чате
    ask_for_img(message.chat.id)


@bot.message_handler(content_types=['photo'])
def get_photo(message):
    global waiting_for_img
    if waiting_for_img:
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
        btn3 = types.InlineKeyboardButton('Выбрать другое изображение', callback_data = 'another_img')
        markup.row(btn1)
        markup.row(btn2)
        markup.row(btn3)
        bot.reply_to(message, 'Изображение принято!\nВыберите вариант прослушивания:', reply_markup=markup)

        waiting_for_img = False


@bot.callback_query_handler(func=lambda call: call.data == 'another_img')
def handle_btn3(callback_query):
    ask_for_img(callback_query.message.chat.id)


# декоратор для обработки callback_data    
@bot.callback_query_handler(func=lambda callback: True)
def callback_message(callback):
    chat_id = callback.message.chat.id
    bot.send_message(chat_id, "Принято!\nИдёт процесс распознавания. Пожалуйста, подождите.")

    img_path = os.path.join('oemer_input', str(chat_id) + ".jpg")
    output_path = os.path.join('oemer_results', str(chat_id))
    if not os.path.exists(output_path):
        os.makedirs(output_path)

    # удаление файлов предыдущего распознавания
    file_list = os.listdir(output_path)
    for file_name in file_list:
        file_path = os.path.join(output_path, file_name)
        os.remove(file_path)

    run_oemer(img_path, output_path)

    # проверка наличия результата распознавания
    xml_path = os.path.join(output_path, str(chat_id) + ".musicxml")
    if not os.path.exists(xml_path):
        bot.send_message(chat_id=chat_id, text="К сожалению, не удалось провести распознавание для данного изображения.")
        ask_for_img(chat_id)
    else:
        if callback.data == 'oemer_all':
            mp3Path = main_converter(xml_path, chat_id)

            bot.send_message(chat_id=chat_id, text="Результат:")
            bot.send_voice(chat_id, voice=open(mp3Path, 'rb'))
        
        if callback.data == 'oemer_parts':
            global waiting_for_number
            all_measures_num = count_measures(xml_path)
            bot.send_message(chat_id=chat_id, text="Сколько тактов вы хотите услышать в одном сообщении?\nВведите цифру.")
            waiting_for_number = True
            # запрос числа тактов в одном файле у пользователя
            @bot.message_handler(func=lambda message: True)
            def handle_message(message):
                global waiting_for_number
                if waiting_for_number:
                    try:
                        measures_per_file = int(message.text)
                        if measures_per_file > all_measures_num:
                            bot.send_message(callback.message.chat.id, "В данном произведении меньшее количество тактов. Введите другое число.")
                        else:
                            waiting_for_number = False
                            bot.send_message(chat_id=chat_id, text="Результат:")
                            measures_sets_dictionary = create_measures_sets_dictionary(all_measures_num, measures_per_file)
                            files_count = 0
                            for name, measures_set in measures_sets_dictionary.items():
                                files_count+=1
                                new_path = os.path.join(output_path, str(chat_id) + "__" + name + ".musicxml")
                                create_mini_musicXML(xml_path, new_path, measures_set)


                                new_mp3Path = main_converter(new_path, chat_id)
                                bot.send_message(chat_id=chat_id, text=str(files_count) + "я часть:")
                                bot.send_voice(chat_id, voice=open(new_mp3Path, 'rb'))
                    except ValueError:
                        bot.send_message(callback.message.chat.id, "Неверный ввод.")


def count_measures(musicXML_path):
    tree = ET.parse(musicXML_path)
    root = tree.getroot()
    # поиск элементов measure в файле
    measures = root.findall('.//measure')
    num_measures = len(measures)
    return num_measures


def create_measures_sets_dictionary(all_measures_num, measures_per_file):
    measures_sets = {}
    current_set = []
    set_num = 1
    for i in range(1, all_measures_num+1):
        current_set.append(str(i))
        if len(current_set) == measures_per_file:
            measures_sets[f"measures_set{set_num}"] = current_set
            current_set = []
            set_num += 1
    if current_set: 
        measures_sets[f"measures_set{set_num}"] = current_set
    return measures_sets


def create_mini_musicXML(musicXML_path, output_path, measures_set):
    tree = ET.parse(musicXML_path)
    root = tree.getroot()
    measures = [measure for measure in root.findall(".//measure") if measure.attrib.get('number') in measures_set]

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
    for measure in measures:
        part.append(measure)

    # добавление элемента attributes в элемент первого такта
    first_measure = new_root.find(".//measure")
    first_measure.insert(0, attributes)

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
    command = f"oemer -o {output_path} {img_path}"
    subprocess.run(command, shell=True)


bot.polling(non_stop=True)
