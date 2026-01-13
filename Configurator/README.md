# Planar Motor Configurator

A web-based configuration tool for designing and managing planar motor production line layouts with Asset Administration Shell (AAS) integration.

## Overview

The Configurator provides a visual interface for arranging production modules on a planar motor system grid. It connects to an AAS infrastructure to dynamically discover available modules and publish layout configurations.

## Features

### Planar Motor Layout Design
- Drag-and-drop interface for placing modules on a 6x5 grid layout
- Visual representation of module areas and flyways
- Real-time position mapping to physical coordinates (millimeters)
- Support for approach and process positions with orientation (yaw)

### AAS Integration
- Dynamic module catalog fetched from AAS Shell Registry
- Displays module metadata including Asset ID, Asset Kind, Asset Type, and AAS ID
- Publishes layout configurations to AAS Repository as HierarchicalStructures submodels
- References module AAS entries via SameAs relationships

### Production Management
- Production order configuration and submission
- Live production view with Xbot tracking
- SOP (Standard Operating Procedure) dashboard
- MQTT connectivity for real-time updates

## Configuration

The application connects to the following services:
- AAS Repository (port 8081): Stores submodels and configuration data
- AAS Shell Registry (port 8082): Discovers available AAS shells and modules
- MQTT Broker (port 8000): Real-time messaging for production updates

Server IP can be configured via the Settings page or environment variables.

## Technology Stack

- React with Vite
- dnd-kit for drag-and-drop functionality
- MQTT.js for broker connectivity
- react-toastify for notifications
