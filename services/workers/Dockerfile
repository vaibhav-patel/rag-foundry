# Fargate / local worker image (ingest pipeline heavy path); Lambda stub uses same repo layout.
FROM public.ecr.aws/lambda/python:3.12

COPY lambda_stub/requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY lambda_stub/*.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.handler"]
