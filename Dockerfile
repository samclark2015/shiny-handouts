FROM python:3.13
RUN apt-get update && apt-get install ffmpeg libsm6 libxext6 ghostscript -y
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
COPY . .
EXPOSE 8080
CMD ["python3", "nice_public.py"]
