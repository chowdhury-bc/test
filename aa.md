provided llm-genai
Context: I am testing Bedrock along side Azure and a locally hosted LLM because I want to understand what we can write that is coupled to a particular CSP and what we can write that is agnostic. For example, the streamlit apps are agnostic and we can lift and shift them easily. What I want to understand now is related to data ingestion portability.
 
Problem: I am trying to use Bedrock via LangChain (python library) to understand a few things about portability. I can not get permissions working related to model validation. (I can get Claude2 to work.) Specifically, I am seeing the following error: "An error occurred (ValidationException) when calling the InvokeModel operation: Invocation of model ID anthropic.claude-3-5-sonnet-20241022-v2:0 with on-demand throughput isn’t supported. Retry your request with the ID or ARN of an inference profile that contains this model."
 
So, I check for what models provide provisioned model throughputs: aws bedrock list-provisioned-model-throughputs and get an empty list. 
 
Who should I chat with on the AWS team about this? I can absolutely see users wanting to access Bedrock this way.
 
