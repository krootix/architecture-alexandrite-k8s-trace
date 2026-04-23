from flask import Flask, request, jsonify
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

resource = Resource.create(attributes={"service.name": "service-b"})

provider = TracerProvider(resource=resource)

endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4318")
otlp_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

trace.set_tracer_provider(provider)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app)

tracer = trace.get_tracer(__name__)
propagator = TraceContextTextMapPropagator()


@app.route('/process', methods=['GET'])
def process():
    # Извлечение контекста из входящих заголовков
    ctx = propagator.extract(request.headers)

    with tracer.start_as_current_span("process-span", context=ctx) as span:
        try:
            value = request.args.get('value', default=1, type=int)
            operation = request.args.get('op', default='double', type=str)

            span.set_attribute("request.value", value)
            span.set_attribute("request.operation", operation)
            span.set_attribute("http.method", "GET")

            logger.info(f"Processing request: value={value}, operation={operation}")

            if operation == 'double':
                result = value * 2
            elif operation == 'square':
                result = value * value
            elif operation == 'half':
                result = value / 2
            else:
                result = value

            span.set_attribute("result", result)

            return jsonify({
                "status": "success",
                "value": value,
                "operation": operation,
                "result": result
            }), 200

        except Exception as e:
            logger.error(f"Error in process: {e}")
            span.record_exception(e)
            return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "service-b"}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)