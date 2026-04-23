from flask import Flask, request, jsonify
import requests
import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Настройка ресурса
resource = Resource.create(attributes={"service.name": "service-a"})

# Создание TracerProvider
provider = TracerProvider(resource=resource)

# OTLP HTTP экспортер
endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
otlp_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

# Установка глобального TracerProvider
trace.set_tracer_provider(provider)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer(__name__)
propagator = TraceContextTextMapPropagator()

SERVICE_B_URL = os.getenv("SERVICE_B_URL", "http://service-b:8080")


def get_hex_trace_id():
    """Получение текущего trace_id в hex формате"""
    span = trace.get_current_span()
    if span is None:
        return None
    trace_id = span.get_span_context().trace_id
    if trace_id is None:
        return None
    return format(trace_id, '032x')


@app.route('/calculate', methods=['GET'])
def calculate():
    with tracer.start_as_current_span("calculate-span") as span:
        try:
            value = request.args.get('value', default=1, type=int)
            operation = request.args.get('op', default='double', type=str)

            span.set_attribute("request.value", value)
            span.set_attribute("request.operation", operation)
            span.set_attribute("http.method", "GET")

            logger.info(f"Processing request: value={value}, operation={operation}")

            # Подготовка заголовков для передачи trace context
            headers = {}
            propagator.inject(headers)

            response = requests.get(
                f"{SERVICE_B_URL}/process",
                params={"value": value, "op": operation},
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            result = response.json()

            span.set_attribute("http.status_code", response.status_code)

            return jsonify({
                "status": "success",
                "value": value,
                "operation": operation,
                "result": result.get("result"),
                "called_service_b": True,
                "trace_id": get_hex_trace_id()
            }), 200

        except requests.exceptions.RequestException as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logger.error(f"Error calling service-b: {e}")
            return jsonify({"status": "error", "error": str(e)}), 500
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "service-a"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)