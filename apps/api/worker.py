"""RQ worker process entrypoint for audit jobs."""

from rq import Worker

from services.audit_queue import AUDIT_QUEUE_NAME, get_redis_connection


def main():
    redis_conn = get_redis_connection()
    worker = Worker([AUDIT_QUEUE_NAME], connection=redis_conn)
    worker.work(with_scheduler=True)


if __name__ == "__main__":
    main()
