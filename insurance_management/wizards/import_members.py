import base64
import csv
import io
import pandas as pd
import logging
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import datetime

_logger = logging.getLogger(__name__)

class ImportMembers(models.TransientModel):
    _name = 'insurance.import.members'
    _description = 'Import Policy Members'

    file = fields.Binary('Member File', required=True)
    file_type = fields.Selection([('csv', 'CSV'), ('excel', 'Excel')], string='File Type', default='excel')

    def action_import(self):
        # Decode the uploaded file
        try:
            data = base64.b64decode(self.file)
            if self.file_type == 'csv':
                # Handle CSV file
                rows = csv.DictReader(io.StringIO(data.decode('utf-8')))
                required_headers = {'name', 'age', 'relation_type', 'unique_identifier'}
                if not rows.fieldnames:
                    raise UserError("CSV file is empty or invalid.")
                missing_headers = required_headers - set(rows.fieldnames)
                if missing_headers:
                    raise UserError(f"Missing required CSV headers: {', '.join(str(h) for h in missing_headers)}")
            elif self.file_type == 'excel':
                # Handle Excel file (.xlsx) with header in first row
                df = pd.read_excel(io.BytesIO(data), header=1)  # Set header to first row (index 0)
                rows = df.to_dict(orient='records')
                required_headers = {'MEMBER NAME*', 'PRIMARY MEMBER NAME*', 'MEM NUMBER*', 'RELATION*', 'DATE OF BIRTH', 'FAMILY SIZE', 'ID NUMBERS', 'PHONE NUMBER', 'EMAIL ADDRESS'}
                if not rows:
                    raise UserError("Excel file is empty or invalid.")
                # Log actual headers for debugging
                actual_headers = set(df.columns)
                _logger.info(f"Actual headers in Excel file: {actual_headers}")
                missing_headers = set(required_headers) - actual_headers
                if missing_headers:
                    raise UserError(f"Missing required Excel headers: {', '.join(str(h) for h in missing_headers)}. Found headers: {', '.join(str(h) for h in actual_headers)}")
            else:
                raise UserError("Unsupported file type. Please select CSV or Excel.")
        except Exception as e:
            raise UserError(f"Error reading file: {str(e)}")

        # Get the policy from the context
        policy = self.env['insurance.policy'].browse(self.env.context.get('active_id'))
        if not policy:
            raise UserError("No policy selected. Please select a policy to import members.")

        # Store created members for linking dependents
        created_members = {}

        # Process each row in the file
        for row in rows:
            try:
                # Log raw row data for debugging
                _logger.info(f"Raw row data: {row}")

                if self.file_type == 'csv':
                    # CSV processing
                    member_vals = {
                        'policy_id': policy.id,
                        'name': row.get('name'),
                        'id_no': row.get('id_no'),
                        'email': row.get('email'),
                        'phone': row.get('phone'),
                        'relation_type': row.get('relation_type', 'principal'),
                        'band_label': row.get('band_label', 'M'),
                        'state': 'pending',
                        'gender': row.get('gender').lower() if row.get('gender') else None,
                        'date_of_birth': datetime.strptime(row.get('date_of_birth', ''), '%Y-%m-%d').date() if row.get('date_of_birth') else None,
                        'unique_identifier': row.get('unique_identifier'),
                    }
                    # Calculate age if date_of_birth is provided
                    age = 0
                    if member_vals['date_of_birth']:
                        today = datetime.now().date()  # 04:05 PM EAT, July 29, 2025
                        age = int(today.year - member_vals['date_of_birth'].year - ((today.month, today.day) < (member_vals['date_of_birth'].month, member_vals['date_of_birth'].day)))
                    member_vals['age'] = age

                    # Validate required fields
                    if not member_vals['name']:
                        raise UserError(f"Missing 'name' in row: {row}")
                    if not member_vals['unique_identifier']:
                        raise UserError(f"Missing 'unique_identifier' in row: {row}")
                    if member_vals['relation_type'] not in ['principal', 'spouse', 'child', 'newborn', 'other']:
                        raise UserError(f"Invalid 'relation_type' in row: {row['relation_type']} (must be 'principal', 'spouse', 'child', 'newborn', or 'other')")
                    if member_vals['gender'] and member_vals['gender'] not in ['male', 'female', 'other']:
                        raise UserError(f"Invalid 'gender' in row: {row['gender']} (must be 'male', 'female', or 'other')")
                    if member_vals['band_label'] != 'M' and member_vals['relation_type'] == 'principal':
                        raise UserError(f"Invalid 'band_label' for principal member in row: {row['band_label']} should be 'M'")

                elif self.file_type == 'excel':
                    # Excel processing
                    member_name = row.get('MEMBER NAME*')
                    principal_name = row.get('PRIMARY MEMBER NAME*')
                    is_dependent = member_name != principal_name if principal_name else False

                    if not member_name:
                        raise UserError(f"Missing 'MEMBER NAME*' in row: {row}")
                    if not row.get('MEM NUMBER*'):
                        raise UserError(f"Missing 'MEM NUMBER*' in row: {row}")
                    if not row.get('RELATION*'):
                        raise UserError(f"Missing 'RELATION*' in row: {row}")
                    if row.get('DATE OF BIRTH') and not isinstance(row.get('DATE OF BIRTH'), datetime):
                        raise UserError(f"Invalid 'DATE OF BIRTH' format in row: {row} (expected date)")
                    if row.get('FAMILY SIZE') not in ['M', 'M+1', 'M+2', 'M+3', 'M+4']:
                        raise UserError(f"Invalid 'FAMILY SIZE' in row: {row} (must be M, M+1, M+2, M+3, or M+4)")

                    # Extract and process gender
                    gender_input = row.get('GENDER')
                    gender = gender_input.lower() if gender_input else None
                    if gender and gender not in ['male', 'female', 'other']:
                        raise UserError(f"Invalid 'gender' in row: {gender_input} (must be 'male', 'female', or 'other')")

                    # Extract and process relation_type
                    relation_input = row.get('RELATION*')
                    relation_type = 'principal' if relation_input and relation_input.upper() == 'SELF' else (relation_input.lower() if relation_input else 'principal')
                    if relation_type not in ['principal', 'spouse', 'child', 'newborn', 'other']:
                        raise UserError(f"Invalid 'relation_type' in row: {relation_input} (must be 'principal', 'spouse', 'child', 'newborn', or 'other')")

                    # Calculate age as integer
                    date_of_birth = row.get('DATE OF BIRTH')
                    age = 0
                    if date_of_birth:
                        today = datetime.now().date()  # 04:05 PM EAT, July 29, 2025
                        age = int(today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day)))

                    member_vals = {
                        'policy_id': policy.id,
                        'name': member_name,
                        'unique_identifier': row.get('MEM NUMBER*'),
                        'relation_type': relation_type,
                        'date_of_birth': date_of_birth.date() if date_of_birth else None,
                        'age': age,
                        'gender': gender,
                        'band_label': row.get('FAMILY SIZE', 'M'),
                        'state': 'pending',
                        'id_no': row.get('ID NUMBERS'),
                        'phone': row.get('PHONE NUMBER'),
                        'email': row.get('EMAIL ADDRESS'),
                    }

                    # Validate required fields
                    if not member_vals['name']:
                        raise UserError(f"Missing 'MEMBER NAME*' in row: {row}")
                    if not member_vals['unique_identifier']:
                        raise UserError(f"Missing 'MEM NUMBER*' in row: {row}")
                    if member_vals['gender'] and member_vals['gender'] not in ['male', 'female', 'other']:
                        raise UserError(f"Invalid 'gender' in row: {row['GENDER']} (must be 'male', 'female', or 'other')")
                    if member_vals['band_label'] != 'M' and member_vals['relation_type'] == 'principal':
                        raise UserError(f"Invalid 'band_label' for principal member in row: {row['FAMILY SIZE']} should be 'M'")

                    if is_dependent and principal_name:
                        # Find or create principal member
                        principal_id = created_members.get(principal_name)
                        if not principal_id:
                            principal_row = next((r for r in rows if r.get('MEMBER NAME*') == principal_name), None)
                            if principal_row:
                                principal_gender_input = principal_row.get('GENDER')
                                principal_gender = principal_gender_input.lower() if principal_gender_input else None
                                if principal_gender and principal_gender not in ['male', 'female', 'other']:
                                    raise UserError(f"Invalid 'gender' in row: {principal_gender_input} (must be 'male', 'female', or 'other')")

                                principal_relation_input = principal_row.get('RELATION*')
                                principal_relation_type = 'principal' if principal_relation_input and principal_relation_input.upper() == 'SELF' else (principal_relation_input.lower() if principal_relation_input else 'principal')
                                if principal_relation_type not in ['principal', 'spouse', 'child', 'newborn', 'other']:
                                    raise UserError(f"Invalid 'relation_type' in row: {principal_relation_input} (must be 'principal', 'spouse', 'child', 'newborn', or 'other')")

                                principal_date_of_birth = principal_row.get('DATE OF BIRTH')
                                principal_age = 0
                                if principal_date_of_birth:
                                    today = datetime.now().date()
                                    principal_age = int(today.year - principal_date_of_birth.year - ((today.month, today.day) < (principal_date_of_birth.month, principal_date_of_birth.day)))

                                principal_vals = {
                                    'policy_id': policy.id,
                                    'name': principal_name,
                                    'unique_identifier': principal_row.get('MEM NUMBER*'),
                                    'relation_type': principal_relation_type,
                                    'date_of_birth': principal_date_of_birth.date() if principal_date_of_birth else None,
                                    'age': principal_age,
                                    'gender': principal_gender,
                                    'band_label': principal_row.get('FAMILY SIZE', 'M'),
                                    'id_no': principal_row.get('ID NUMBERS'),
                                    'phone': principal_row.get('PHONE NUMBER'),
                                    'email': principal_row.get('EMAIL ADDRESS'),
                                    'state': 'pending',
                                }
                                new_principal = self.env['insurance.policy.member'].create(principal_vals)
                                principal_id = new_principal.id
                                created_members[principal_name] = principal_id
                        member_vals['principal_member_id'] = principal_id

                # Create the member
                new_member = self.env['insurance.policy.member'].create(member_vals)
                if self.file_type == 'excel' and not is_dependent:
                    created_members[member_name] = new_member.id


            except ValueError as ve:
                raise UserError(f"Error processing row {row}: Invalid value (e.g., age must be an integer, date must be valid). {str(ve)}")
            except Exception as e:
                raise UserError(f"Error processing row {row}: {str(e)}")

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'insurance.policy',
            'view_mode': 'form',
            'res_id': policy.id,
            'target': 'current',
        }