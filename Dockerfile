# our base image
FROM python:3-onbuild

# specify the port number the container should expose
EXPOSE 5000

#ENV FLASK_ENV="development"

# run the application
CMD ["python", "./app.py"]