FROM python:3.10.17-alpine3.21

WORKDIR /usr/src/app

COPY requirements.txt .

# Install build tools temporarily, install deps, then clean up
RUN apk add --no-cache --virtual .build-deps \
        gcc musl-dev libffi-dev openssl-dev cargo rust \
    && apk add --no-cache ffmpeg \
    && pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps

# Add runtime libs needed by compiled deps like tiktoken
RUN apk add --no-cache libgcc libstdc++

COPY . .

# Run multiple Python scripts in order
CMD ["/bin/sh", "-c", "python3 app.py && python3 main.py && python3 upload_video.py --file='podcast_video.mp4' --title='Upload public video using python scrip & Docker' --description='This is first video uploaded using a Python script & Docker' --keywords='podcast, business news'"]

