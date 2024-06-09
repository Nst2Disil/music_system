FROM huecker.io/library/python:3.12

WORKDIR /app

RUN apt-get update && apt-get install -y ffmpeg fluid-soundfont-gm fluidsynth

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot.py"]