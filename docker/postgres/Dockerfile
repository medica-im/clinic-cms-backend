FROM postgres:14

ARG USER_ID
ARG GROUP_ID
# Digest of the postgres:14 base this image was built from, recorded so
# deploys can detect an upstream update without rebuilding.
ARG BASE_DIGEST=""
LABEL base.digest="${BASE_DIGEST}"

RUN if [ ${USER_ID:-0} -ne 0 ] && [ ${GROUP_ID:-0} -ne 0 ]; then \
    userdel -f postgres &&\
    if getent group postgres ; then groupdel postgres; fi &&\
    groupadd -g ${GROUP_ID} postgres &&\
    useradd -l -u ${USER_ID} -g postgres --home-dir=/var/lib/postgresql postgres &&\
    chown --changes --silent --no-dereference --recursive \
          --from=999:999 ${USER_ID}:${GROUP_ID} \
    /var/lib/postgresql \
    /var/lib/postgresql/data \
    /var/run/postgresql \
;fi
        
USER postgres