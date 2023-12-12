import boto3
import cfnresponse
import time
import json
import requests
import os
from os import environ

#Global variables used in composing the URL as in CAPI
accept = "application/json"
content_type = "application/json"

#This section is commented until/if Redis CAPI will support status update while creating imports.

# runtime_region = os.environ['AWS_REGION']
# stepfunctions = boto3.client("stepfunctions")

def lambda_handler (event, context):
    
    #The event that is sent from CloudFormation. Displayed in CloudWatch logs.
    print (event)
    
    #This section is commented until/if Redis CAPI will support status update while creating imports.
    
    # aws_account_id = context.invoked_function_arn.split(":")[4]
    
    #Creating the callEvent dictionary that will be identical with a Swagger API call
    callEvent = {}
    if "sourceType" in event['ResourceProperties']:
        callEvent["sourceType"] = event['ResourceProperties']["sourceType"]
    importFromUriList = []
    if "importFromUri" in event['ResourceProperties']:
        importFromUriList.append(event['ResourceProperties']["importFromUri"])
        callEvent["importFromUri"] = importFromUriList
        
    print ("callEvent that is used as the actual API Call is bellow:")
    print (callEvent)
    
    subscription_id = event['ResourceProperties']["subscriptionId"]
    print ("Subscription ID is: " + str(subscription_id))
    database_id = event['ResourceProperties']["databaseId"]
    print ("Database ID is: " + str(database_id))
    
    #Additional global variables used in methods for URL composing or as credentials to login.
    global stack_name
    global base_url
    global x_api_key
    global x_api_secret_key 
    base_url = event['ResourceProperties']['baseURL']
    x_api_key =  RetrieveSecret("redis/x_api_key")["x_api_key"]
    x_api_secret_key =  RetrieveSecret("redis/x_api_secret_key")["x_api_secret_key"]
    stack_name = str(event['StackId'].split("/")[1])
    
    #Creating the CloudFormation response block. Presuming the status as SUCCESS. If an error occurs, the status is changed to FAILED.
    responseData = {}
    responseStatus = 'SUCCESS'
    responseURL = event['ResponseURL']
    responseBody = {'Status': responseStatus,
                    'PhysicalResourceId': context.log_stream_name,
                    'StackId': event['StackId'],
                    'RequestId': event['RequestId'],
                    'LogicalResourceId': event['LogicalResourceId']
                    }
    
    #If the action of CloudFormation is Create stack                
    if event['RequestType'] == "Create":
        #The API Call the creates the Import
        try:
            responseValue = PostImport(callEvent, subscription_id, database_id)
            print ("This is the responseValue")
            print (responseValue)
            
            #This section is commented until/if Redis CAPI will support status update while creating backup.
            
            # SFinput = {}
            # SFinput["responseBody"] = responseBody
            # SFinput["responseURL"] = responseURL
            # SFinput["base_url"] = event['ResourceProperties']['baseURL']
            # response = stepfunctions.start_execution(
            #     stateMachineArn = f'arn:aws:states:{runtime_region}:{aws_account_id}:stateMachine:FlexibleDatabaseImport-StateMachine-{runtime_region}-{stack_name}',
            #     name = f'FlexibleDatabaseImport-StateMachine-{runtime_region}-{stack_name}',
            #     input = json.dumps(SFinput)
            #     )
            # print ("Output sent to Step Functions is the following:")
            # print (json.dumps(SFinput))           
            
            #Checking if the process was success or failure
            status = CheckStatus(responseValue['links'][0]['href'])
            #Populate Outputs tab of the stack
            if "processing-completed" in status:
                responseData.update({"SubscriptionId":str(subscription_id), "DatabaseId":str(database_id), "PostCall":str(callEvent)})
                responseBody.update({"Data":responseData})
                GetResponse(responseURL, responseBody)
            else:
                #If any error is encounter in the "try" block, then a function will catch the error and throw it back to CloudFormation as a failure reason.
                responseStatus = 'FAILED'
                reason = status
                if responseStatus == 'FAILED':
                    responseBody.update({"Status":responseStatus})
                    if "Reason" in str(responseBody):
                        responseBody.update({"Reason":reason})
                    else:
                        responseBody["Reason"] = reason
                    GetResponse(responseURL, responseBody)

        except:
                #This except block is triggered only for wrong base_url or wrong credentials.
                responseStatus = 'FAILED'
                reason = 'Please check if the base_url or the credentials set in Secrets Manager are wrong.'
                if responseStatus == 'FAILED':
                    responseBody.update({"Status":responseStatus})
                    if "Reason" in str(responseBody):
                        responseBody.update({"Reason":reason})
                    else:
                        responseBody["Reason"] = reason
                    GetResponse(responseURL, responseBody)
    
    #If the action of CloudFormation is Update stack, CloudFormation will receive a success response
    if event['RequestType'] == "Update":
        #Retrieve parameters from Outputs tab of the stack and appending the dictionary with the PhysicalResourceId which is a required parameter for Update actions
        cf_sub_id, cf_db_id, cf_event = CurrentOutputs()
        PhysicalResourceId = event['PhysicalResourceId']
        responseBody.update({"PhysicalResourceId":PhysicalResourceId})
        responseStatus = 'SUCCESS'
        responseBody.update({"Status":responseStatus})
        responseData.update({"SubscriptionId":str(subscription_id), "DatabaseId":str(database_id), "PostCall":str(callEvent)})
        responseBody.update({"Data":responseData})
        GetResponse(responseURL, responseBody)
    
    #If the action of CloudFormation is Delete stack, CloudFormation will receive a success response    
    if event['RequestType'] == "Delete":
        cf_sub_id, cf_db_id, cf_event = CurrentOutputs()
        responseStatus = 'SUCCESS'
        responseBody.update({"Status":responseStatus})
        responseData.update({"SubscriptionId":str(subscription_id), "DatabaseId":str(database_id), "PostCall":str(callEvent)})
        responseBody.update({"Data":responseData})
        GetResponse(responseURL, responseBody)

#This function retrieves x_api_key and x_api_secret_key from Secrets Manager service and returns them in the function as variables    
def RetrieveSecret(secret_name):
    headers = {"X-Aws-Parameters-Secrets-Token": os.environ.get('AWS_SESSION_TOKEN')}

    secrets_extension_endpoint = "http://localhost:2773/secretsmanager/get?secretId=" + str(secret_name)
    r = requests.get(secrets_extension_endpoint, headers=headers)
    secret = json.loads(r.text)["SecretString"]
    secret = json.loads(secret)

    return secret 

#This function retrieves the parameters from Outputs tab of the stack to be used later    
def CurrentOutputs():
    cloudformation = boto3.client('cloudformation')
    cf_response = cloudformation.describe_stacks(StackName=stack_name)
    for output in cf_response["Stacks"][0]["Outputs"]:
        if "SubscriptionId" in str(output): 
            cf_sub_id = output["OutputValue"]

        if "PostCall" in str(output): 
            cf_event = output["OutputValue"]

        if "DatabaseId" in str(output): 
            cf_db_id = output["OutputValue"]
            
    print ("cf_sub_id is: " + str(cf_sub_id))
    print ("cf_event is: " + str(cf_event))
    print ("cf_db_id is: " + str(cf_db_id))
    return cf_sub_id, cf_db_id, cf_event  

#Makes the POST API call to create the import       
def PostImport (event, subscription_id, database_id):
    url = base_url + "/v1/subscriptions/" + str(subscription_id) + "/databases/" + str(database_id) + "/import"
    
    response = requests.post(url, headers={"accept":accept, "x-api-key":x_api_key, "x-api-secret-key":x_api_secret_key, "Content-Type":content_type}, json = event)
    response_json = response.json()
    return response_json
    Logs(response_json)   

#Checks if the import is completed and if it is successfull or failed   
def CheckStatus (url):
    response = requests.get(url, headers={"accept":accept, "x-api-key":x_api_key, "x-api-secret-key":x_api_secret_key})
    response = response.json()
    count = 0

    while "processing-completed" not in str(response) or count < 120:
        time.sleep(1)
        count += 1
        response = requests.get(url, headers={"accept":accept, "x-api-key":x_api_key, "x-api-secret-key":x_api_secret_key})
        response = response.json()
        
    if "processing-completed" in response["status"]:
        status = response["status"]
    if "processing-error" in response["status"]:
        status = response["response"]["error"]["description"]

    return str(status)

#Send response back to CloudFormation       
def GetResponse(responseURL, responseBody): 
    responseBody = json.dumps(responseBody)
    req = requests.put(responseURL, data = responseBody)
    print ('RESPONSE BODY:n' + responseBody)

#Checks if there is an error in the description    
def Logs(response_json):
    error_url = response_json['links'][0]['href']
    error_message = requests.get(error_url, headers={"accept":accept, "x-api-key":x_api_key, "x-api-secret-key":x_api_secret_key})
    error_message_json = error_message.json()
    if 'description' in error_message_json:
        while response_json['description'] == error_message_json['description']:
            error_message = requests.get(error_url, headers={"accept":accept, "x-api-key":x_api_key, "x-api-secret-key":x_api_secret_key})
            error_message_json = error_message.json()
        print(error_message_json)
    else:
        print ("No errors")
    
