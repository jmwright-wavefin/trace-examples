import threading
from pprint import pprint

import requests
from ddtrace import tracer
from ddtrace.propagation.http import HTTPPropagator
from flask import Flask, jsonify, request

# Initialize the first server
app1 = Flask(__name__)
app2 = Flask(__name__)

# set an environ variable
import os

# Try setting the environment variable to add ALL baggage as span tags
os.environ["DD_TRACE_BAGGAGE_TAG_KEYS"] = "*"


@app1.route("/send", methods=["POST"])
def send_request():
    # Start a new span and set baggage
    with tracer.trace("first_server") as span:
        # Unpack baggage headers
        incoming_headers = dict(request.headers)
        prior_context = HTTPPropagator.extract(incoming_headers)
        print("send_request#incoming_baggage: ", prior_context.get_all_baggage_items())
        for i, (k, v) in enumerate(prior_context.get_all_baggage_items().items()):
            span.context.set_baggage_item(k, v)

        # Test set_baggage_item
        span.context.set_baggage_item("baggage-app-1", "baggage-value-1")

        # Test get_all_baggage_items()
        all_baggage = span.context.get_all_baggage_items()
        print("send_request#all_baggage: ", all_baggage)

        # Inject the context into the headers
        outgoing_headers = {
            "header-baggage-from-app1": "baggage-value-1",
        }
        HTTPPropagator.inject(span.context, outgoing_headers)

        # Example request body
        data = {"message": "Hello from the first server!"}

        # Send the request to the second server
        response = requests.post(
            "http://localhost:5001/receive",
            headers=outgoing_headers,
            json=data,
            timeout=5,
        )

        # Print the response
        print("send_request#response: ", response.text)

        # Test remove_all_baggage_items()
        span.context.remove_all_baggage_items()
        print(
            "send_request#remove_all_baggage_items: ",
            span.context.get_all_baggage_items(),
        )

        return jsonify({"status": "Example complete"}), 200


@app2.route("/receive", methods=["POST"])
def receive_request():
    # Extract the context from the incoming request headers
    incoming_headers = dict(request.headers)
    print("receive_request#incoming_headers: ")
    pprint(incoming_headers)

    context = HTTPPropagator.extract(incoming_headers)
    # Try activating the context since the span had a different context
    tracer.context_provider.activate(context)

    # Test get_all_baggage_items
    all_baggage = context.get_all_baggage_items()
    print("receive_request#all_baggage: ", all_baggage)

    with tracer.trace("custom_span") as span:
        # Set a manual tag and also print tags
        span.set_tag("app2_manual_span_tag", "app2_span_value")
        print("receive_request#custom_span.tags: ", span.get_tags())

    return jsonify({"all_baggage": all_baggage}), 200


# Function to run the first Flask app
def run_app1():
    app1.run(port=5000)  # Specify the port for the first app


# Function to run the second Flask app
def run_app2():
    app2.run(port=5001)  # Specify the port for the second app


if __name__ == "__main__":
    threading.Thread(target=run_app1).start()
    threading.Thread(target=run_app2).start()

    # make request to first server with baggage
    with tracer.trace("initiator") as span:
        span.context.set_baggage_item("baggage-from-initiator", "some-value")
        # Try setting the user.id baggage item since Datadog has this as a default
        # here: https://ddtrace.readthedocs.io/en/v3.7.1/configuration.html#DD_TRACE_BAGGAGE_TAG_KEYS
        span.context.set_baggage_item("user.id", "bob")
        headers = {}
        HTTPPropagator.inject(span.context, headers)
        requests.post("http://localhost:5000/send", headers=headers, timeout=5)
