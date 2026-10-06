# PetDesk Appointments ETL

Has 2 solutions. A single file version and a package version

## Version 1 : Single file

```bash
python solution.py
python solution.py --page-size 2 --db-path appointments.db
python solution.py --dry-run
python solution.py --test
```

## Version 2 : Package

```bash
cp .env.sample .env
python -m etl
python -m etl --page-size 2
python -m etl --dry-run
python -m unittest
```

With pipenv: `pipenv run etl`, `pipenv run solution`, `pipenv run test`.

Settings are read from `.env` or environment variables (see `.env.sample`). Logs are written to `logs/etl.log`.
Each run is recorded in the `pipeline_runs` table.

## Docker

Writes data to Docker volume named etl-data

```bash
docker build -t petdesk-etl .
docker run --rm -v etl-data:/data petdesk-etl
```

In Git Bash, run `export MSYS_NO_PATHCONV=1` first.

## Kubernetes

```bash
minikube start
minikube image build -t petdesk-etl:latest .
kubectl apply -f k8s/etl.yaml
kubectl create job --from=cronjob/petdesk-etl etl-now
kubectl logs -f job/etl-now
kubectl create job --from=cronjob/petdesk-etl-dry-run etl-dry-run
kubectl logs -f job/etl-dry-run
```

Rerun `minikube image build` after code changes. Delete old jobs before reusing a name: `kubectl delete job etl-now etl-dry-run`.
