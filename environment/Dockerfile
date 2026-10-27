ARG REGISTRY_HOST
FROM $REGISTRY_HOST/codeocean/mambaforge3:23.1.0-4-python3.10.12-ubuntu22.04

ARG DEBIAN_FRONTEND=noninteractive
ARG AWS_ACCESS_KEY_ID
ARG AWS_DEFAULT_REGION
ARG AWS_SECRET_ACCESS_KEY

RUN pip install -U --no-cache-dir \
    aind-data-schema==2.9.2 \
    aind-data-schema-models==6.3.1 \
    pynrrd==1.1.3 \
    h5py==3.12.1 \
    s3fs==2023.9.2
