#!/bin/bash
set -eu

KC=/opt/keycloak/bin/kcadm.sh

"$KC" config credentials \
    --server http://keycloak:8080 \
    --realm master \
    --user "$KEYCLOAK_ADMIN" \
    --password "$KEYCLOAK_ADMIN_PASSWORD"

get_scope_id() {
    "$KC" get client-scopes -r soa --fields id,name \
        | grep -B 1 -F "\"name\" : \"$1\"" \
        | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' | head -n 1
}

email_scope_id=$(get_scope_id email)
if [ -z "$email_scope_id" ]; then
    "$KC" create client-scopes -r soa \
        -b '{"name":"email","description":"Include the authenticated user email in tokens","protocol":"openid-connect","attributes":{"include.in.token.scope":"true","display.on.consent.screen":"true"}}' >/dev/null
    email_scope_id=$(get_scope_id email)
fi

if ! "$KC" get "client-scopes/$email_scope_id/protocol-mappers/models" -r soa --fields name \
    | grep -q '"name" : "email"'; then
    "$KC" create "client-scopes/$email_scope_id/protocol-mappers/models" -r soa \
        -b '{"name":"email","protocol":"openid-connect","protocolMapper":"oidc-usermodel-property-mapper","consentRequired":false,"config":{"user.attribute":"email","claim.name":"email","jsonType.label":"String","id.token.claim":"true","access.token.claim":"true","userinfo.token.claim":"true"}}' >/dev/null
fi

basic_scope_id=$(get_scope_id basic)
if [ -z "$basic_scope_id" ]; then
    "$KC" create client-scopes -r soa \
        -b '{"name":"basic","description":"Include the authenticated subject in access tokens","protocol":"openid-connect","attributes":{"include.in.token.scope":"false","display.on.consent.screen":"false"}}' >/dev/null
    basic_scope_id=$(get_scope_id basic)
fi

if ! "$KC" get "client-scopes/$basic_scope_id/protocol-mappers/models" -r soa --fields name \
    | grep -q '"name" : "sub"'; then
    "$KC" create "client-scopes/$basic_scope_id/protocol-mappers/models" -r soa \
        -b '{"name":"sub","protocol":"openid-connect","protocolMapper":"oidc-sub-mapper","consentRequired":false,"config":{"access.token.claim":"true","introspection.token.claim":"true"}}' >/dev/null
fi

audience_scope_id=$(get_scope_id todo-api-audience)
if [ -z "$audience_scope_id" ]; then
    "$KC" create client-scopes -r soa \
        -b '{"name":"todo-api-audience","description":"Include the SOAlab API as an access-token audience","protocol":"openid-connect","attributes":{"include.in.token.scope":"false","display.on.consent.screen":"false"}}' >/dev/null
    audience_scope_id=$(get_scope_id todo-api-audience)
fi

audience_mapper_id=$("$KC" get "client-scopes/$audience_scope_id/protocol-mappers/models" -r soa --fields id,name \
    | grep -B 1 -E '"name" : "SOAlab API (custom )?audience"' \
    | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' | head -n 1 | tr -d '\r')
audience_mapper='{"name":"SOAlab API custom audience","protocol":"openid-connect","protocolMapper":"oidc-audience-mapper","consentRequired":false,"config":{"included.custom.audience":"todo-api","access.token.claim":"true","id.token.claim":"false"}}'
if [ -n "$audience_mapper_id" ]; then
    "$KC" update "client-scopes/$audience_scope_id/protocol-mappers/models/$audience_mapper_id" -r soa \
        -b "{\"id\":\"$audience_mapper_id\",\"name\":\"SOAlab API custom audience\",\"protocol\":\"openid-connect\",\"protocolMapper\":\"oidc-audience-mapper\",\"consentRequired\":false,\"config\":{\"included.custom.audience\":\"todo-api\",\"access.token.claim\":\"true\",\"id.token.claim\":\"false\"}}" >/dev/null
else
    "$KC" create "client-scopes/$audience_scope_id/protocol-mappers/models" -r soa \
        -b "$audience_mapper" >/dev/null
fi

for client_name in soa-postman cad-kpi-client; do
    client_id=$("$KC" get clients -r soa -q "clientId=$client_name" --fields id \
        | sed -n 's/.*"id" : "\([^"]*\)".*/\1/p' | head -n 1)
    if [ -z "$client_id" ]; then
        echo "OAuth client $client_name is missing" >&2
        exit 1
    fi
    "$KC" update "clients/$client_id/optional-client-scopes/$email_scope_id" -r soa >/dev/null
    "$KC" update "clients/$client_id/default-client-scopes/$basic_scope_id" -r soa >/dev/null
    "$KC" update "clients/$client_id/default-client-scopes/$audience_scope_id" -r soa >/dev/null
    echo "Configured basic, email, and API audience scopes for $client_name"
done

if [ -z "${ATLASSIAN_CLIENT_ID:-}" ] || [ -z "${ATLASSIAN_CLIENT_SECRET:-}" ]; then
    echo "Atlassian IdP not configured; set ATLASSIAN_CLIENT_ID and ATLASSIAN_CLIENT_SECRET to enable it."
    exit 0
fi

if "$KC" get identity-provider/instances/atlassian -r soa >/dev/null 2>&1; then
    action=update
    endpoint=identity-provider/instances/atlassian
else
    action=create
    endpoint=identity-provider/instances
fi

"$KC" "$action" "$endpoint" \
    -r soa \
    -s alias=atlassian \
    -s providerId=oauth2 \
    -s displayName=Atlassian \
    -s enabled=true \
    -s trustEmail=false \
    -s 'config.clientId='"$ATLASSIAN_CLIENT_ID" \
    -s 'config.clientSecret='"$ATLASSIAN_CLIENT_SECRET" \
    -s 'config.authorizationUrl=https://auth.atlassian.com/authorize?audience=api.atlassian.com&prompt=consent' \
    -s config.tokenUrl=https://auth.atlassian.com/oauth/token \
    -s config.userInfoUrl=https://api.atlassian.com/me \
    -s config.defaultScope=read:me \
    -s config.userIDClaim=account_id \
    -s config.userNameClaim=email \
    -s config.clientAuthMethod=client_secret_post \
    -s config.syncMode=IMPORT
