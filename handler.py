import runpod

def handler(job):

    job_id = job["id"]  # Access the job ID from the request
    job_input = job["input"]  # Access the input from the request

    print(f"Hello World! This is a test job. {job_id}")  # Log a message for debugging
    print("Received job input:", job_input)  # Log the input for debugging

    # Add your custom code here to process the input

    return "Your job results"

runpod.serverless.start({"handler": handler})  # Required