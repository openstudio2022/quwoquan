FROM scratch

COPY . /evidence

# The bundle is never started, but docker create requires an image command before
# docker cp can materialize /evidence by exact digest.
CMD ["/evidence"]
