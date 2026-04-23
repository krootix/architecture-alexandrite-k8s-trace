#!/bin/bash

echo "=== Запуск Minikube ==="
minikube delete
minikube start --cpus=2 --memory=4096 --addons=ingress

echo "=== Создание namespace ==="
kubectl create namespace observability

echo "=== Развертывание Jaeger (без оператора) ==="
kubectl apply -f k8s/jaeger-instance.yaml

echo "=== Ожидание готовности Jaeger ==="
kubectl wait --for=condition=ready --timeout=300s pod -l app=jaeger -n observability

echo "=== Сборка образов сервисов ==="
minikube image build -t service-a:latest services/service-a/
minikube image build -t service-b:latest services/service-b/

echo "=== Развертывание OpenTelemetry Collector ==="
kubectl apply -f k8s/opentelemetry-collector.yaml

echo "=== Развертывание сервисов ==="
kubectl apply -f k8s/services.yaml

echo "=== Ожидание готовности подов ==="
kubectl wait --for=condition=ready --timeout=300s pod -l app=otel-collector -n observability
kubectl wait --for=condition=ready --timeout=300s pod -l app=service-a -n observability
kubectl wait --for=condition=ready --timeout=300s pod -l app=service-b -n observability

echo "=== Деплой завершен ==="
echo ""
echo "Для доступа к Jaeger UI выполните:"
echo "kubectl port-forward svc/jaeger 16686:16686 -n observability"
echo ""
echo "Для доступа к Service A:"
echo "kubectl port-forward svc/service-a 8080:8080 -n observability"
echo ""
echo "Для тестирования выполните:"
echo "curl http://localhost:8080/calculate?value=5&op=square"