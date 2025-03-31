# OurFamilyWizard Message Extractor

## Overview
This utility tool extracts and processes message chains from OurFamilyWizard's Message Reports, separating consolidated message exports into individual messages for improved readability and analysis.

## Purpose
OurFamilyWizard is a co-parenting communication platform that allows parents to export message threads as reports. However, these exports often combine multiple messages into a single document. This tool parses these reports and breaks them down into discrete messages, making communication history easier to review, analyze, and reference.

## Features
- Parses OurFamilyWizard Message Reports
- Separates consolidated message threads into individual messages
- Preserves message metadata (timestamps, sender information)
- Maintains message formatting and content integrity
- Simplifies review of communication history

## Installation
```bash
# Clone the repository
git clone https://github.com/username/OurFamilyWizard_message_extractor.git

# Navigate to the project directory
cd OurFamilyWizard_message_extractor

# Install dependencies (if applicable)
# pip install -r requirements.txt
```

## Usage
```bash
# Basic usage
python message_extractor.py path/to/exported_message_report.pdf

# For additional options
python message_extractor.py --help
```

## Input Format
The tool expects message reports exported from the OurFamilyWizard platform. To generate these reports:
1. Log in to your OurFamilyWizard account
2. Navigate to the Messages section
3. Select the conversation thread you wish to export
4. Use the "Create Message Report" feature
5. Save the generated report

## Output Format
The tool will create individual message files in a structured format, preserving:
- Message timestamp
- Sender information
- Message content
- Attachments (if applicable)

## Use Cases
- Legal proceedings requiring communication evidence
- Maintaining organized records of co-parenting communications
- Simplified review of communication history
- Documentation for family mediators or counselors

## Disclaimer
This tool is an independent utility designed to help users manage their exported message data from the OurFamilyWizard® service. It is not affiliated with, endorsed by, or connected to OurFamilyWizard. OurFamilyWizard® is a registered trademark of OurFamilyWizard.
