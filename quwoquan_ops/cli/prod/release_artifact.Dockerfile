FROM scratch

COPY . /release

CMD ["/release/manifest.json"]
