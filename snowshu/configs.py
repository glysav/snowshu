from pathlib import Path
from shutil import which
import os

PACKAGE_ROOT=Path().parent.absolute()
MAX_ALLOWED_DATABASES=2000
MAX_ALLOWED_ROWS=1000000
DEFAULT_INSERT_CHUNK_SIZE=50000
DEFAULT_THREAD_COUNT=4
DOCKER_NETWORK='snowshu'
DOCKER_TARGET_CONTAINER='snowshu_target'
DOCKER_TARGET_PORT=9999


def _is_in_docker()->bool:
    ## running horizontal, 
    ## this should work for Unix AND Windows https://stackoverflow.com/questions/36765138/bind-to-docker-socket-on-windows
    if os.path.exists(os.path.join('var','run','docker.sock')) and not which('docker'):
        return True
    ## running vertical (not recommended)
    with open('/proc/1/cgroup', 'rt') as ifh:
        return any([indicator in line for line in ifh.readlines() for indicator in ('docker','kubepods',)])
IS_IN_DOCKER=_is_in_docker()
