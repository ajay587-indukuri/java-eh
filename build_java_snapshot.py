import asyncio
from datetime import timedelta

from dotenv import load_dotenv
from vercel import sandbox
from vercel.sandbox import NetworkPolicy

load_dotenv(".env.local")


async def main():
    box = await sandbox.create_sandbox(
        execution_time_limit=timedelta(minutes=15),
        persistent=False,
        env={},
    )
    try:
        await box.run_command("apt-get", ["update", "-qq"], sudo=True, check=True)
        await box.run_command(
            "apt-get",
            ["install", "-y", "--no-install-recommends", "openjdk-17-jdk-headless"],
            sudo=True,
            check=True,
        )
        await box.update_network_policy(NetworkPolicy.deny_all())
        snapshot = await box.snapshot(expiration=0)
    finally:
        await box.destroy()

    print(f"JAVA_SNAPSHOT_ID={snapshot.id}")


if __name__ == "__main__":
    asyncio.run(main())
