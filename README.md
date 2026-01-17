# Gatewise Spoof

Create a fake Gatewise app I can share with family that will let them open the gate to my apartment complex

## Repository layout

- gatewise.php - The final result
- docs/TODO.txt - TODO list from beginning of project to end
- pki - MITM PKI generation script
- nginx - MITM docker compose project w/ python proxy
- logs - Various artifacts from reverse engineering
- curl - PoC in curl
- apk - Gatewise app source

## Secrets

Once you get the Gatewise firebase API key, put it in ./secrets/web-api-key.txt

Once you get the Firebase ID refresh token, put it in ./secrets/refresh-token.txt
