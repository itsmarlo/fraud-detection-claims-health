# Bruno environments

Open this directory as a Bruno collection and select an environment:

- `local`: direct Uvicorn server at `http://localhost:8000`
- `btp`: deployed SAP BTP Cloud Foundry application route

For the `btp` environment, replace `BASE_URL` with the route returned by:

```bash
cf app health-fraud-detection-agent
```

Recommended request order:

1. `Health`
2. `Score High-Priority Claim`
3. `Score Routine-Priority Claim`

Each request contains Bruno tests for the expected HTTP status and response.
The API currently has no application authentication. Do not store Cloud
Foundry passwords, service keys, or other credentials in this collection.
