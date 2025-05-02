# Fargate / local worker image (ingest pipeline heavy path); Lambda stub uses same repo layout.
FROM public.ecr.aws/lambda/python:3.12

COPY lambda_stub/handler.py ${LAMBDA_TASK_ROOT}/handler.py

CMD ["handler.handler"]
