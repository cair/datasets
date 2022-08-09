import abc
import pathlib
import subprocess
import logging
import sys

import httpx
import tomli_w
import tomli

FORMAT = '%(asctime)s  %(message)s'
logging.basicConfig(format=FORMAT)

_LOGGER = logging.getLogger(__file__)
_LOGGER.setLevel(logging.DEBUG)

current_path = pathlib.Path(__file__).parent


def read_toml(path: pathlib.Path):
    with open(path, "rb") as f:
        toml_dict = tomli.load(f)
    return toml_dict


def write_toml(path: pathlib.Path, doc: dict):
    with open(path, "wb") as f:
        tomli_w.dump(doc, f)
    return doc


def subprocess_stream(*args, **kwargs):
    process = subprocess.Popen(*args, **kwargs, stdout=subprocess.PIPE)
    for c in iter(process.stdout.readline, b''):
        sys.stdout.buffer.write(c)


def check_output(*args, **kwargs):
    output = subprocess.check_output(
        *args, **kwargs
    )
    return output.decode("utf-8").strip()


class IPFSClientImpl:

    @abc.abstractmethod
    def add(self, dataset_path: pathlib.Path):
        raise NotImplementedError

    @abc.abstractmethod
    def get(self, hash_: str, save_location: pathlib.Path = None):
        raise NotImplementedError

    @abc.abstractmethod
    def get_http(self, hash_: str, save_location: pathlib.Path = None):
        raise NotImplementedError


class IPFSClientLinux(IPFSClientImpl):

    def __init__(self, gateway):
        self._gateway = gateway
        self._binary_which = pathlib.Path("/usr/bin/which")
        if not self._binary_which.exists():
            raise RuntimeError(f"Could not find {str(self._binary_which)}")

        self._binary_ipfs = self.check_ipfs_binary()
        self._max_retry = 10

    def check_ipfs_binary(self):
        output = check_output(
            [str(self._binary_which.absolute()), "ipfs"],
            stderr=subprocess.STDOUT,
            shell=False
        )
        return pathlib.Path(output)

    def add(self, dataset_path: pathlib.Path):
        items = []
        repository_path = dataset_path.parent.parent

        for file in [x for x in dataset_path.iterdir() if x.is_file()]:
            output = check_output(
                [str(self._binary_ipfs), "add", "--recursive", "-q", str(file.absolute())]
            )

            # add item pair (path and hash)
            item = (str(file.relative_to(repository_path)), output)
            items.append(item)

        return items

    def get(self, hash_: str, save_location: pathlib.Path = None):

        cmd = [str(self._binary_ipfs), "get", hash_]

        if save_location is not None:
            cmd += ["--output", str(save_location.absolute())]

        subprocess_stream(cmd)
        return True

    def get_http(self, hash_: str, save_location: pathlib.Path = None, retry=0):

        response = httpx.get(f"{self._gateway}/ipfs/{hash_}", timeout=300)

        if response.status_code == 200:
            with open(save_location, "wb+") as f:
                f.write(response.content)
        else:
            if retry >= self._max_retry:
                return False

            return self.get_http(hash_, save_location, retry=retry + 1)
        return True


class IPFSClient:

    def __init__(self, http_gateway="https://cloudflare-ipfs.com", http=False):
        self.instance = IPFSClientLinux(gateway=http_gateway)
        self._has_ipfs_binary = self.instance.check_ipfs_binary()
        self._gateway = http_gateway
        self._force_http = http

    def add(self, dataset_path: pathlib.Path):
        return self.instance.add(dataset_path)

    def get(self, hash_: str, save_location=None):
        if self._force_http:
            return self.instance.get_http(hash_, save_location)
        elif self._has_ipfs_binary:
            return self.instance.get(hash_, save_location)


def add_repositories(repository_path: pathlib.Path):
    for dataset in [x for x in repository_path.iterdir() if x.is_dir()]:
        ipfs = IPFSClient()
        _LOGGER.info(f"Processing {dataset}")
        dataset_files = dataset.joinpath("data")
        metadata_path = dataset.joinpath("metadata.toml")

        if dataset_files.exists():
            _LOGGER.info("Found dataset files. Uploading files to IPFS.")

            # Publish data to IPFS
            hashes = ipfs.add(dataset_files)

            if len(hashes) == 0:
                continue

            # Update metadata
            _LOGGER.info(f"Updating metadata {metadata_path} for dataset {dataset.name}")
            metadata_doc = read_toml(metadata_path)
            metadata_doc["files"] = hashes
            write_toml(metadata_path, metadata_doc)


def retrieve_repository(repository_path: pathlib.Path, dataset: str = "iris", http_gateway=None, http=True):
    if http_gateway:
        ipfs = IPFSClient(http_gateway=http_gateway, http=http)
    else:
        ipfs = IPFSClient(http=http)
    dataset_path = repository_path.joinpath(dataset)
    dataset_info = read_toml(dataset_path.joinpath("metadata.toml"))

    for (file, ipfs_hash) in dataset_info["files"]:
        file_path = repository_path.joinpath(file)
        if not file_path.parent.exists():
            # Path to the file does not exist. create
            file_path.parent.mkdir(exist_ok=True)

        ipfs.get(ipfs_hash, save_location=file_path)


if __name__ == "__main__":
    path = pathlib.Path(__file__).parent.joinpath("repository")

    add_repositories(repository_path=path)
    retrieve_repository(repository_path=path, dataset="iris")
