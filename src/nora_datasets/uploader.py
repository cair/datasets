import pathlib
import subprocess
import logging
import sys

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


class IPFSWrapperLinux:

    def __init__(self):
        self._binary_which = pathlib.Path("/usr/bin/which")
        if not self._binary_which.exists():
            raise RuntimeError(f"Could not find {str(self._binary_which)}")

        self._binary_ipfs = self._check_ipfs_binary()

    def _check_ipfs_binary(self):
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
        return None


class IPFSWrapper:

    def __init__(self):
        self.instance = IPFSWrapperLinux()

    def add(self, dataset_path: pathlib.Path):
        return self.instance.add(dataset_path)

    def get(self, hash_: str, save_location=None):
        return self.instance.get(hash_, save_location)


def example_add_repositories(ipfs, repository_path: pathlib.Path):
    for dataset in [x for x in repository_path.iterdir() if x.is_dir()]:
        _LOGGER.info(f"Processing {dataset}")
        dataset_files = dataset.joinpath("data")
        metadata_path = dataset.joinpath("metadata.toml")

        if dataset_files.exists():
            _LOGGER.info("Found dataset files. Uploading files to IPFS.")

            # Publish data to IPFS
            hashes = ipfs.add(dataset_files)

            # Update metadata
            _LOGGER.info(f"Updating metadata {metadata_path} for dataset {dataset.name}")
            metadata_doc = read_toml(metadata_path)
            metadata_doc["files"] = hashes
            write_toml(metadata_path, metadata_doc)


def example_retrieve_repository(ipfs, repository_path: pathlib.Path, dataset: str = "iris"):
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

    ipfs = IPFSWrapper()

    example_add_repositories(ipfs, repository_path=path)
    example_retrieve_repository(ipfs, repository_path=path, dataset="iris")
