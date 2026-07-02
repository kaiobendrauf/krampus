# krampus
A SANTA sync server working with a firestore database

## Local Development
Here's how you get set up with the local development environment:
1. `docker compose up --build`
2. That's it!

### Accessing MySQL in the local environment
1. Go to http://localhost:8094
2. Use the credentials for `krampus_rw` from the Docker compose file to log in. This account has permissions in the `krampus` database.