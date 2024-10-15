<p align="center">
  <p align="center">
    <img src="https://nng.alonas.lv/img/logo.svg" height="100">
  </p>
  <h1 align="center">nng fastapi</h1>
</p>

[![License badge](https://img.shields.io/badge/license-EUPL-blue.svg)](LICENSE)
[![Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Docker Build and Push](https://github.com/thealonas/nng-fastapi/actions/workflows/docker.yml/badge.svg)](https://github.com/thealonas/nng-fastapi/actions/workflows/docker.yml)

A platform for coordinating all nng microservices.

### Installation

Use a pre-built [Docker container](https://github.com/orgs/thealonas/packages/container/package/nng-fastapi).

### Configuration

The main configuration is done through the environment variables.

* `NNG_API_SK` - Secret JWT key for encryption
* `OP_CONNECT_HOST` - Link to 1Password Connect server
* `OP_CONNECT_TOKEN` - 1Password Connect token
