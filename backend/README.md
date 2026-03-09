# StateTracker module:

RepoManager.py - manages repositories and is called everytime something changes in a users repo locally. 
It stores the file structure and local dev states like this 

repo -> branch -> file_states -> base_commit -> dev_id -> patch 

base commit is the commit identifies of the last time the user synced with the remote repository. So for example if a user does git pull,
their base commit is head. 

a patch is a representation of the changes the user made to a file. A developer can have multiple patches for the same file in the same branchonly if for example they have two local repositories for the same github repo but with different base commits and on the same branch. 

FileCache.py - Fetches file content of a certain commit from git and caches it, uses LRU cache. We need this because we can't correctly simulate merges without the base content of the file. 

FileStates.py - manages file states. It stores the file path for a specific branch, if within this branch multipls devs are working on different base commits (on this file), then each dev will have their own patch for that file per base commit. So inside FileStates we have a dictionary of base commits, and for each base commit we have a dictionary of dev_ids and their patches. 

GitMock.py - mock git implementation. Applies git diffs to base content of file to get the content of file on users local repo. Simulates git merges to check for conflicts. 


Running the backend:

if you don't have uv installed do: pip install uv  (or you can just use pip)

first time only:

uv init

uv venv

source .venv/bin/activate (on mac)

on every pull do:

uv pip install -r requirements.txt

run:

uv run run.py


To run and test the GitHub App functionality (webhooks), use smee.io to forward events to localhost.

# 1. Install smee-client
npm install --global smee-client

# 2. Run the forwarder
This forwards webhooks from our shared channel to your local server
smee -u https://smee.io/NyJnB4mesbF3DVAp -t http://localhost:8000/webhooks/github

Make sure your backend is running on port 8000.