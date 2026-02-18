# Assistent Adapter SPI

## Purpose

Adapter SPI enables non-invasive integration with external channels (Feishu/OpenClaw and future channels).

## Core Interface

`AssistentAdapterSpi`:

- `adapterId`
- `verify(headers, rawBody)`
- `ingest(headers, rawBody)`
- `dispatch(sourceEvent, responseEnvelope)`

## Runtime

`AssistentAdapterRuntime`:

- `parseIncoming(adapterId, headers, rawBody)`
- `dispatch(adapterId, sourceEvent, responseEnvelope)`

## Registry

`AssistentAdapterRegistry`:

- register adapter
- query by id
- list adapters

## Integration Rules

- Core engine does not import channel SDK directly.
- Adapter validates source signatures and converts to normalized event.
- Response dispatch can be text/card/stream payload depending on channel.

