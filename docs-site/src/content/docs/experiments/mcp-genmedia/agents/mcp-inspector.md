---
title: "MCP Inspector usage"
---

You can use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to test the Genmedia MCP servers.


An example config file is provided where you can use veo-go, nanobanana-go, or chirp3-go as your server.

```bash
npx @modelcontextprotocol/inspector --config genmedia-config.json --server veo-go
```

Please note the example file has a few configurations you'll want to change

* `PROJECT_ID` per genmedia service, set your Google Cloud Project ID
* `GENMEDIA_BUCKET` this is optional, and if you set it, this will be used as the default Google Cloud Storag bucket for created assets

## Veo & Lyria

Veo will require a slightly longer timeout, so please start with a `MCP_SERVER_REQUEST_TIMEOUT` of 50 seconds (50000ms).



```bash
export MCP_SERVER_REQUEST_TIMEOUT=55000
npx @modelcontextprotocol/inspector
```