# Configure Amazon Cognito for SupportPilot

This guide connects an Amazon Cognito user pool to the API token verifier and optional Streamlit Hosted UI sign-in. Keep the project on local synthetic data until the user pool, trusted tenant assignment, HTTPS entry point, and remaining [production readiness items](production_readiness.md) are in place.

## Token and tenant contract

The API accepts **Cognito access tokens** only. It validates the token signature against the user pool JWKS and checks `iss`, `exp`, `token_use=access`, and `client_id`. If you use a Cognito resource-server binding that adds `aud`, configure the exact `COGNITO_RESOURCE_AUDIENCE` value as well. AWS documents that access tokens use `client_id` and `token_use`, and that Cognito user pools publish their signing keys through JWKS ([JWT verification](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html), [access token claims](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html)).

Every API access token must carry a signed `tenant_id` claim. The provided trigger reads `custom:tenant_id` from the Cognito user's attributes and copies it into the access token. Assign that attribute through an administrator-controlled provisioning process. Do not give the public app client write permission for it, and do not accept tenant IDs from registration forms or client metadata.

## Configure the user pool

1. Create or select a Cognito user pool and app client. Use a **public app client with no client secret**, enable the authorization-code grant and PKCE, and allow `openid`, `email`, and the custom `support/approve` scope. Create a resource server identifier `support` with scope `approve`. Register the callback URL `http://localhost:8501` and sign-out URL `http://localhost:8501/?signed_out=1` for local testing. Use a user pool issuer in this form:

   ```text
   https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
   ```

2. Add a string custom attribute named `tenant_id` to the user pool schema. Cognito presents it to triggers as `custom:tenant_id`.
3. Create the Cognito user group `SupportReviewers`; assign membership only through an administrator-controlled process. The trigger adds `support/approve` only to that group's access tokens and suppresses it for other users.
4. Configure the app client's attribute permissions so end users cannot write `custom:tenant_id`. Use an administrator-managed process to assign each user's tenant.
5. Package `infra/cognito/pre_token_generation.py` as a Python Lambda deployment package, create the Lambda function, set `COGNITO_APPROVAL_SCOPE=support/approve` and `COGNITO_REVIEWER_GROUP=SupportReviewers`, and allow Cognito to invoke it.
6. In the user pool's **Pre token generation** trigger settings, select the Lambda function and event version **V2_0** (basic features plus access-token customization for user identities). V1 events cannot add this access-token claim or customize its scopes. AWS documents that access-token customization requires V2 or V3; those versions are available on Essentials or Plus feature plans, with M2M trigger behavior requiring V3 ([pre-token generation trigger](https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-lambda-pre-token-generation.html)). Check current Cognito plan pricing before enabling paid features.
7. Use a Cognito test event in the Lambda console. Verify the returned `tenant_id` equals the user's assigned tenant, `support/approve` appears only for `SupportReviewers`, and an absent or malformed tenant fails closed.
8. Configure deployment values outside Git:

   ```text
   APP_ENV=production
   AUTH_ENABLED=true
   COGNITO_ISSUER=https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
   COGNITO_APP_CLIENT_ID=<app-client-id>
   COGNITO_TENANT_CLAIM=tenant_id
   COGNITO_APPROVAL_SCOPE=support/approve
   SUPPORTPILOT_COGNITO_DOMAIN=https://<your-cognito-domain>.auth.<region>.amazoncognito.com
   SUPPORTPILOT_COGNITO_CLIENT_ID=<same-public-app-client-id>
   SUPPORTPILOT_COGNITO_REDIRECT_URI=http://localhost:8501
   SUPPORTPILOT_COGNITO_LOGOUT_URI=http://localhost:8501/?signed_out=1
   SUPPORTPILOT_COGNITO_SCOPES=openid email support/approve
   ```

   Set `COGNITO_RESOURCE_AUDIENCE` only if you configure resource-bound access tokens. Use the issuer URL exactly as it appears in the token's `iss` claim.

## Verify the integration

- Obtain a short-lived **access token** from the configured Cognito sign-in flow. Do not use the ID token.
- Confirm the access token's verified claims include the expected issuer, app-client ID, `token_use=access`, and administrator-assigned `tenant_id`.
- With the UI settings configured, open `http://localhost:8501`, choose **Start sign-in**, then **Sign in with Cognito**. The UI uses authorization code with PKCE, refreshes tokens when needed, and clears session tokens after Cognito redirects back from logout.
- Verify a request for the token's tenant succeeds and a request naming a different tenant returns HTTP 403. Missing, expired, wrong-client, ID, or tenant-less tokens must return HTTP 401.
- Confirm app-client users cannot edit `custom:tenant_id`; otherwise tenant authorization can be self-assigned and is not trustworthy.
- Confirm Cognito group membership is administrator-controlled. The pre-token trigger suppresses `support/approve` for non-reviewers and grants it to the `SupportReviewers` group. Authenticated users without that scope can work within their tenant but receive HTTP 403 when submitting approval decisions. The local auth-disabled demo bypasses this check.

No real user pool has been configured or tested in this repository yet. When Hosted UI settings are blank, local Compose retains the manual access-token field and `AUTH_ENABLED=false` demo behavior. For actual sign-in, enable API authentication and provide valid Cognito configuration. OAuth PKCE transactions and Streamlit session tokens are held in the UI process's memory, so use a single UI instance for this demo; production needs HTTPS and a reviewed shared session/token store and deployment setup.
