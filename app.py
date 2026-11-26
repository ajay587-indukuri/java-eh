import asyncio
import io
import os
import subprocess
import tempfile
from datetime import timedelta
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
APP_DIR = Path(__file__).resolve().parent
MAX_CODE_CHARS = 30_000
MAX_OUTPUT_BYTES = 16_000
LOCAL_TIMEOUT_SECONDS = 10
SANDBOX_TIMEOUT_SECONDS = 10

EXCEPTION_EXPLANATIONS = (
    ("ArithmeticException", "Arithmetic error. Usually caused by division by zero."),
    ("NullPointerException", "A null object was accessed."),
    ("ArrayIndexOutOfBoundsException", "An invalid array index was accessed."),
    ("StringIndexOutOfBoundsException", "An invalid position in a string was accessed."),
    ("IndexOutOfBoundsException", "An index outside the valid range was accessed."),
    ("NumberFormatException", "Invalid number format during conversion."),
    ("InputMismatchException", "Input does not match the expected data type."),
    ("ClassCastException", "An object was converted to an incompatible type."),
    ("IllegalArgumentException", "An illegal argument was passed to a method."),
    ("IllegalStateException", "A method was called in an invalid state."),
    ("NegativeArraySizeException", "An array was created with a negative size."),
    ("ArrayStoreException", "An incompatible value was stored in an array."),
    ("ConcurrentModificationException", "A collection was modified unexpectedly while iterating."),
    ("NoSuchElementException", "The requested element does not exist."),
    ("EmptyStackException", "An operation was performed on an empty stack."),
    ("UnsupportedOperationException", "The requested operation is not supported."),
    ("SecurityException", "The operation was blocked by security restrictions."),
    ("StackOverflowError", "Stack memory overflow. Possible infinite recursion."),
    ("OutOfMemoryError", "The Java program ran out of available memory."),
    ("AssertionError", "An assertion condition failed."),
    ("ClassNotFoundException", "The specified class could not be found."),
    ("NoClassDefFoundError", "A required class was missing at runtime."),
    ("NoSuchMethodException", "The requested method could not be found."),
    ("NoSuchFieldException", "The requested field could not be found."),
    ("IllegalAccessException", "Access to a class or member was not permitted."),
    ("InstantiationException", "The class could not be instantiated."),
    ("AbstractMethodError", "An abstract method was not properly implemented."),
    ("NoSuchMethodError", "A required method was missing at runtime."),
    ("NoSuchFieldError", "A required field was missing at runtime."),
    ("LinkageError", "A Java class linking problem occurred."),
    ("FileNotFoundException", "The requested file could not be found."),
    ("EOFException", "Unexpected end of file or input stream."),
    ("InterruptedIOException", "An input/output operation was interrupted."),
    ("MalformedURLException", "The URL format is invalid."),
    ("UnknownHostException", "The host name could not be resolved."),
    ("SocketTimeoutException", "The network connection timed out."),
    ("SocketException", "A network socket error occurred."),
    ("ProtocolException", "A network protocol error occurred."),
    ("SQLException", "A database operation failed."),
    ("InterruptedException", "The thread was interrupted during execution."),
    ("IllegalMonitorStateException", "Invalid thread monitor or synchronization usage."),
    ("RejectedExecutionException", "The task was rejected for execution."),
    ("DateTimeParseException", "The date or time could not be parsed."),
    ("DateTimeException", "An invalid date or time value was used."),
    ("ParseException", "The supplied data could not be parsed."),
    ("FormatterException", "An error occurred while formatting data."),
    ("CharacterCodingException", "Character encoding or decoding failed."),
    ("IOException", "An input/output operation failed."),
    ("RuntimeException", "An unexpected runtime error occurred."),
    ("Exception handled. Continuing program...", "Exception handled successfully. Program continued."),
    ("Unhandled Exception:", "An unhandled exception occurred."),
    ("Exception", "An exception occurred during program execution."),
    ("Error", "A serious Java error occurred."),
)


class CappedOutput(io.BytesIO):
    def __init__(self, limit=MAX_OUTPUT_BYTES):
        super().__init__()
        self.limit = limit
        self.truncated = False

    def write(self, value):
        remaining = max(0, self.limit - self.tell())
        super().write(value[:remaining])
        self.truncated |= len(value) > remaining
        return len(value)

    def text(self):
        return self.getvalue().decode("utf-8", errors="replace")


def _explanation(output):
    for marker, explanation in EXCEPTION_EXPLANATIONS:
        if marker in output:
            return explanation
    return "Program executed successfully."


def _support_sources():
    return {
        "EH.java": (APP_DIR / "eh.java").read_text(encoding="utf-8"),
        "Runner.java": (APP_DIR / "runner.java").read_text(encoding="utf-8"),
    }


def _run_locally(code):
    with tempfile.TemporaryDirectory() as folder:
        source_dir = Path(folder)
        (source_dir / "Main.java").write_text(code, encoding="utf-8")
        for name, content in _support_sources().items():
            (source_dir / name).write_text(content, encoding="utf-8")

        try:
            compile_result = subprocess.run(
                ["javac", "Main.java", "EH.java", "Runner.java"],
                cwd=source_dir,
                capture_output=True,
                text=True,
                timeout=LOCAL_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {
                "output": "Compilation exceeded the 10-second time limit.",
                "explanation": "The Java compiler did not finish in time.",
            }

        if compile_result.returncode != 0:
            return {
                "output": compile_result.stdout + compile_result.stderr,
                "explanation": "Compilation error. Check your Java code.",
            }

        try:
            result = subprocess.run(
                ["java", "-Xmx256m", "-XX:ActiveProcessorCount=1", "Runner"],
                cwd=source_dir,
                capture_output=True,
                text=True,
                timeout=LOCAL_TIMEOUT_SECONDS,
                check=False,
            )
            output = result.stdout + result.stderr
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            output = stdout + stderr
            output += "\n[Execution stopped after the 10-second time limit.]"

        if len(output) > MAX_OUTPUT_BYTES:
            output = output[:MAX_OUTPUT_BYTES] + "\n[Output truncated.]"
        return {"output": output, "explanation": _explanation(output)}


async def _run_in_sandbox(code, snapshot_id):
    from vercel import sandbox
    from vercel.sandbox import NetworkPolicy, SandboxResources, SnapshotSource

    compile_output = CappedOutput(limit=8_000)
    async with sandbox.create_sandbox(
        source=SnapshotSource(snapshot_id=snapshot_id),
        network_policy=NetworkPolicy.deny_all(),
        execution_time_limit=timedelta(seconds=40),
        resources=SandboxResources(vcpus=1, memory=2048),
        env={},
        persistent=False,
    ) as box:
        await box.fs.mkdir("submission")
        async with box.fs.batch(cwd="submission") as batch:
            batch.write_text("Main.java", code)
            for name, content in _support_sources().items():
                batch.write_text(name, content)

        compile_result = await box.run_process(
            "javac",
            ["Main.java", "EH.java", "Runner.java"],
            cwd="submission",
            stdout=compile_output,
            stderr=subprocess.STDOUT,
            kill_after=SANDBOX_TIMEOUT_SECONDS,
        )
        if compile_result.returncode != 0:
            output = compile_output.text() or "Compilation did not complete."
            return {
                "output": output,
                "explanation": "Compilation error. Check your Java code.",
            }

        output = CappedOutput()
        await box.run_process(
            "java",
            ["-Xmx256m", "-XX:ActiveProcessorCount=1", "Runner"],
            cwd="submission",
            stdout=output,
            stderr=subprocess.STDOUT,
            kill_after=SANDBOX_TIMEOUT_SECONDS,
        )

    result = output.text()
    if output.truncated:
        result += "\n[Output truncated.]"
    return {"output": result, "explanation": _explanation(result)}


@app.route("/")
def home():
    return send_from_directory(APP_DIR, "index.html")


@app.route("/runner")
def runner():
    return send_from_directory(APP_DIR, "runner.html")


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({
        "output": "The request exceeds the maximum supported size.",
        "explanation": "Shorten the Java source and try again.",
    }), 413


@app.route("/run", methods=["POST"])
def run_code():
    payload = request.get_json(silent=True)
    code = payload.get("code") if isinstance(payload, dict) else None
    if not isinstance(code, str) or not code.strip():
        return jsonify({
            "output": "Provide Java source code in the request.",
            "explanation": "The code field must be a non-empty string.",
        }), 400
    if len(code) > MAX_CODE_CHARS:
        return jsonify({
            "output": "The Java source exceeds the 30,000-character limit.",
            "explanation": "Shorten the source code and try again.",
        }), 413

    if os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"):
        snapshot_id = os.environ.get("JAVA_SNAPSHOT_ID")
        if not snapshot_id:
            app.logger.error("JAVA_SNAPSHOT_ID is not configured.")
            return jsonify({
                "output": "The Java runner is not configured yet.",
                "explanation": "The deployment is missing its Java sandbox snapshot.",
            }), 503
        try:
            result = asyncio.run(_run_in_sandbox(code, snapshot_id))
        except Exception:
            app.logger.exception("Java sandbox execution failed.")
            return jsonify({
                "output": "The isolated Java runner is temporarily unavailable.",
                "explanation": "The sandbox could not start or complete this run. Try again shortly.",
            }), 503
    else:
        result = _run_locally(code)

    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
