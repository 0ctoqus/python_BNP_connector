FROM yukinying/chrome-headless-browser-selenium

USER root

# set working directory
WORKDIR "/myapp"

# install packages
RUN apt-get update
RUN apt-get -y install python3-pip libmariadbclient-dev
ADD requirements.txt .
RUN python3 -m pip install -r requirements.txt

# copy data
COPY digits/ ./digits/

# run the script
ADD mechanize.py .

ENTRYPOINT []
CMD ["python3", "mechanize.py"]