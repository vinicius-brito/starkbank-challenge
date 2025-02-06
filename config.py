from starkbank import Project

PRIVATE_KEY = open("./keys/private-key.pem", "r").read()
PROJECT_ID = "6482151570669568"

def get_starkbank_user():
    return Project(
        environment="sandbox",
        id=PROJECT_ID,
        private_key=PRIVATE_KEY
    )