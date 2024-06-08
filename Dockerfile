FROM huecker.io/library/python:3.12

RUN pip install oemer
WORKDIR /app

ENTRYPOINT ["oemer"]    