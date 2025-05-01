FROM python:3.11
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6  -y
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY . .
EXPOSE 8080
CMD ["shiny", "run", "app.py", "--host", "0.0.0.0", "--port", "8080"]