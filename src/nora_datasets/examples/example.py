from nora_datasets import retrieve_repository
import pathlib
if __name__ == "__main__":
    repository_path = pathlib.Path(__file__).parent.parent.joinpath("repository")
    retrieve_repository(repository_path=repository_path, dataset="iris", http=True)
