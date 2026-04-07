import json, uuid,requests,os
from odoo import models, fields, api,http
from odoo.exceptions import UserError
from . import report_builder
from PyPDF2 import PdfFileWriter, PdfFileReader
import tempfile
import base64
from PIL import Image
import io
import time
import zipfile
from odoo.tools.translate import _
import html2text
FIELD_TYPES = [(key, key) for key in sorted(fields.Field._by_type__)]
import  uuid, json
from reportbro import Report, ReportBroError

class ReportPrintMixin(models.AbstractModel):
	_name = 'report.print.mixin'
	_description = 'Report Print Mixin'

	def _register_hook(self):

		def GetUrl(self):
			self.env.cr.execute("select value  from ir_config_parameter where key ='web.base.url'")
			dicts = self.env.cr.dictfetchall()
			return str(dicts[0]['value'])

		def getOdooToken(self):

			session = http.request.session
			session_id = session.sid
			return session_id

		def generate_report(**kwargs):
			env = kwargs.get('env')
			report_definition = kwargs.get('report')
			data_list = kwargs.get('data_list')
			add_fonts = kwargs.get('add_fonts')
			c_f = kwargs.get('c_f')
			key_list=[]
			try:
				for tmp in data_list:
					json_data = tmp[0]
					s_id=tmp[1]
					if json_data is None:
						raise UserError(_('Invalid request'))
					output_format = json_data.get('outputFormat')
					if output_format not in ('pdf', 'xlsx'):
						raise UserError(_('Invalid output format: %(format)s. Must be pdf or xlsx') % {
							'format': output_format
						})
					data = json_data.get('data')

					try:
						data = eval(str(json.dumps(data)).replace('false', 'None'))
					except Exception as e:
						print(f"请求数据处理错误: {e}")
					is_test_data = bool(json_data.get('isTestData'))
					try:
						report = Report(report_definition, data, is_test_data, encode_error_handling='replace',additional_fonts=add_fonts,custom_functions=c_f)
					except Exception as e:
						raise UserError(_('Failed to initialize report: %(error)s') % {
							'error': str(e)
						})
					if report.errors:

						raise UserError(_('Report errors: %(errors)s') % {
							'errors': ', '.join(report.errors)
						})

					try:
						key = str(uuid.uuid4())
						report_file_pdf = None
						report_file_xlsx = None

						if output_format == 'pdf':
							report_file_pdf = bytes(report.generate_pdf())
						elif output_format == 'xlsx':
							report_file_xlsx = bytes(report.generate_xlsx())
						if env['report.temp'].search_count([('p_key', '=', key)]) == 0:
							env['report.temp'].create(
								{'p_key': key, 'report_file_pdf': report_file_pdf, 'report_file_xlsx': report_file_xlsx})
						key_list.append({'key': key, 's_id': s_id})

					except ReportBroError as err:
						raise UserError(_('Report generation error: %(error)s') % {
							'error': err.error
						})
				return key_list
			except Exception as e:
				raise UserError(_('Report generation failed: %(error)s') % {
					'error': str(e)
				})

		def report_pdf_prints(self, args, types):
			report_id = args
			print_type =types
			data_id = self.env.context.get('active_ids', None)
			report_report = self.env['report.report'].browse(report_id)
			data_model=self.env.context.get('active_model', None)
			data_model_details=report_report.model_detail_id.model if report_report.report_type=='bill' else ''
			if data_model is  None:
				raise UserError(_('Failed to obtain data source'))
			res_id = self.env[data_model]._read_group(
				domain=[('id', 'in', data_id)],
				groupby=[report_report.group_field],
				aggregates=[f"{report_report.group_field}:count"]
			)

			generated_keys = []
			data_list = []
			add_fonts = self.env['report.font'].sudo().get_reportbro_fonts()
			c_f = self.env['report.report.fun'].sudo().get_fun_list()
			try:
				report = json.loads(report_report.report_data)
			except (json.JSONDecodeError, TypeError, ValueError) as e:
				raise UserError(
					_("Error, the report template is empty. Please design the report template first:%s") % e)
			for s_code in res_id:
				s_id = []
				group_field_name = report_report.group_field
				group_value = s_code[0]
				try:
					wheres_id = self.env[data_model].search([('id', 'in', data_id), (group_field_name, '=', group_value)])
				except Exception as e:
					raise UserError(_('Data query failed:%s')% str(e) )
				for wid in wheres_id:
					s_id.append(wid.id)
				dic = {}

				dic['data'] = report_builder.ReportDataProcessor.get_data(self,report_id,s_id,data_model,data_model_details,report_report.model_main_key)
				dic['outputFormat'] = print_type
				dic['isTestData'] = True
				data_list.append([dic, s_id])
			res = generate_report(env=self.env, data_list=data_list, add_fonts=add_fonts, c_f=c_f, report=report)
			if res:
				generated_keys = res
			self.env.cr.commit()

			if len(generated_keys) > 1:
				all_records = self.env['report.temp'].sudo().search([
					('p_key', 'in', [item['key'] for item in generated_keys])
				])
				if print_type == 'pdf':
					pdf_bytes_list = [record.report_file_pdf for record in all_records if record.report_file_pdf]
					pdf_writer = PdfFileWriter()

					for pdf_bytes in pdf_bytes_list:
						pdf_reader = PdfFileReader(io.BytesIO(pdf_bytes))
						numPages = pdf_reader.getNumPages()
						for index in range(0, numPages):
							pageObj = pdf_reader.getPage(index)
							pdf_writer.addPage(pageObj)

					output_buffer = io.BytesIO()
					pdf_writer.write(output_buffer)
					final_content = output_buffer.getvalue()

					key_uid = str(uuid.uuid4())
					self.env['report.temp'].create({'p_key': key_uid, 'report_file_pdf': final_content})
				elif print_type == 'xlsx':
					zip_buffer = io.BytesIO()
					with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
						for item in generated_keys:
							record = all_records.filtered(lambda r: r.p_key == item['key'])

							if record and record.report_file_xlsx:
								if item['s_id']:
									filename = f"{item['s_id'][0]}.xlsx"
								else:
									filename = f"{record.id}.xlsx"
								zip_file.writestr(filename, record.report_file_xlsx)

					final_content = zip_buffer.getvalue()

					key_uid = str(uuid.uuid4())
					self.env['report.temp'].create({
						'p_key': key_uid,
						'report_file_xlsx': final_content
					})
					print_type='zip'
				file_name = int(time.time())
			else:
				key_uid = generated_keys[0]['key']
				s_id_list = generated_keys[0]['s_id']
				if s_id_list:
					file_name = s_id_list[0]
				else:
					file_name = int(time.time())

			if print_type == 'pdf':
				report_temp = self.env['report.temp'].sudo().search([
					('p_key', '=', key_uid)
				], limit=1)
				report_file_bytes = report_temp.report_file_pdf
				url= f'{self.GetUrl()}/tpstudio/report/report_server/run?key={key_uid}&outputFormat={print_type}&report_id={args}&filename={file_name}'
				return report_file_bytes,file_name,print_type,url

			else:
				report_temp = self.env['report.temp'].sudo().search([
					('p_key', '=', key_uid)
				], limit=1)
				report_file_bytes = report_temp.report_file_xlsx
				url=f"{self.GetUrl()}/tpstudio/report/report_server/run?key={key_uid}&outputFormat={print_type}&report_id={args}&filename={file_name}"
				return report_file_bytes,file_name,print_type,url

		models.BaseModel.GetUrl = GetUrl
		models.BaseModel.report_pdf_prints = report_pdf_prints

		return super(ReportPrintMixin, self)._register_hook()

class ReportTemp(models.TransientModel):
	_name = 'report.temp'
	_description = 'Report Temp'

	p_key=fields.Char('Content key')
	report_file_pdf= fields.Binary('PDF', attachment=False)
	report_file_xlsx = fields.Binary('XLSX',attachment=False)
	print_status=fields.Boolean('print status',default=False)
	name=fields.Html('preview',store=False,sanitize=False)

class ReportReport(models.Model):
	_name = "report.report"
	_description = "Report"

	name = fields.Char(string='Report Name', required=True)
	model_id = fields.Many2one('ir.model', string='Main Model', ondelete="cascade",help='At Least One Data Model Must Exist',readonly=True)
	model_detail_id = fields.Many2one('ir.model', string='Detail Table Model', ondelete="cascade",readonly=True)
	report = fields.Text(string='Report')
	model_main_key = fields.Char(
		string="Main table associated fields",
		help="Many2one Field in Detail Model Pointing to Main Table, e.g., order_id, move_id, picking_id"
	)
	model_ids = fields.One2many('report.report.main', 'report_main_id', string='Main Model Fields')
	model_detail_ids = fields.One2many('report.report.detail', 'report_detail_id', string='Detail field')
	display_complete = fields.Boolean(string='add action', default=False)
	display_completes = fields.Boolean(string='Add Actions in Bulk', default=False)
	reset_designer = fields.Boolean(string='Redesign', default=False, help='Redesign using a new template. All previous layout settings will be cleared.')
	report_data = fields.Text('Report Data')
	data_source = fields.Char(string='Data Source')
	test_data = fields.Text('data structure')
	pdf_name=fields.Text('PDF Name')
	report_type=fields.Selection(selection=[('bill','Document'),('report','Report')],string='Report Type',help='Reports with a main model and a detail model are document-type reports.')
	group_field=fields.Char(string='Batch Print Identifier',help='Field Used to Distinguish Documents in Batch Printing')
	output_format = fields.Selection(
		selection=[('pdf', 'PDF'), ('xlsx', 'Excel')],
		string='Output Format',
		default='pdf',
		help='Choose the output format for this report'
	)
	available_detail_model_ids = fields.Many2many(
		'ir.model',
		compute='_compute_available_detail_models',
		string='Available Detail Models'
	)
	used_font_ids = fields.Many2many(
		'report.font',
		'report_font_report_rel',
		'report_id',
		'font_id',
		string='Used Fonts'
	)
	action_report_id = fields.Many2one(
		'ir.actions.report',
		string='Print Action',
		ondelete='cascade',  # 或 'set null'
		help='Associated print action'
	)

	def get_output_format(self, action_id):
		if isinstance(action_id, int):
			action_id = action_id
		elif hasattr(action_id, 'id'):
			# 是 recordset，提取 ID
			action_id = action_id.id
		else:
			return self.env['report.report']

		report = self.search([
			('action_report_id', '=', action_id)
		], limit=1)
		return report.output_format if report else None

	def action_import_full_config(self, file_datas=None):

		self.ensure_one()

		if not file_datas:
			raise UserError(_('Please select the file to import'))

		try:
			decoded_bytes = base64.b64decode(file_datas)
			decoded_content = decoded_bytes.decode('utf-8')

			imported_data = json.loads(decoded_content)

			if isinstance(imported_data, dict) and 'content' in imported_data:
				config_data = imported_data['content']
				metadata = imported_data.get('metadata', {})
			else:
				config_data = imported_data
				metadata = {}

			if 'report' not in config_data:
				raise UserError(_('The configuration file is missing report data'))

			report_config = config_data['report']
			main_fields = config_data.get('main_fields', [])
			detail_fields = config_data.get('detail_fields', [])

			model_id = self._get_model_id_by_name(report_config.get('model_name'))
			model_detail_id = self._get_model_id_by_name(report_config.get('model_detail_name'))

			if not model_id:
				raise UserError(_("Model not found: %s")% report_config.get('model_name'))

			values = {
				'model_id': model_id,
				'model_detail_id': model_detail_id,
				'model_main_key': report_config.get('model_main_key'),
				'group_field': report_config.get('group_field'),
				'report_type': report_config.get('report_type'),
				'report_data': report_config.get('report_data'),
				'output_format': report_config.get('output_format'),
			}

			self.write(values)
			failed_count = 0
			failed_fields = []


			if main_fields:
				self.model_ids.unlink()

				for field_data in main_fields:
					field_id_obj = field_data.get('field_id', {})
					field_name = field_id_obj.get('name')
					field_model = field_id_obj.get('model')

					field_id = self._get_field_id_by_name(field_model, field_name)

					if not field_id:
						failed_count += 1
						failed_fields.append(field_name)
						continue

					# if not field_id:
					# 	raise UserError(_("Field not found: %s. %s") % (field_model,field_name))

					self.env['report.report.main'].create({
						'report_main_id': self.id,
						'model_id': model_id,
						'field_id': field_id,
						'field_params': field_data.get('field_params'),
						'field_value': field_data.get('field_value'),
						'is_report': field_data.get('is_report', True),
						'field_path': field_data.get('field_path'),
						'level': field_data.get('level', 0),
					})

			if detail_fields:
				self.model_detail_ids.unlink()

				for field_data in detail_fields:
					field_id_obj = field_data.get('field_id', {})
					field_name = field_id_obj.get('name')
					field_model = field_id_obj.get('model')

					field_id = self._get_field_id_by_name(field_model, field_name)

					if not field_id:
						failed_count += 1
						failed_fields.append(field_name)
						continue

					# if not field_id:
					# 	raise UserError(_("Field not found: %s. %s") % (field_model,field_name))

					self.env['report.report.detail'].create({
						'report_detail_id': self.id,
						'model_id': model_id,
						'field_id': field_id,
						'field_params': field_data.get('field_params'),
						'field_value': field_data.get('field_value'),
						'is_report': field_data.get('is_report', True),
						'field_path': field_data.get('field_path'),
						'level': field_data.get('level', 0),
					})
			if failed_count>0:
				max_preview = 10

				fields_preview = failed_fields[:max_preview]
				more_text = f"\n... and {len(failed_fields) - max_preview} more" if len(
					failed_fields) > max_preview else ''
				return {
					'message': _(
						'Report configuration imported to: "%s"<br/>'
						'- failed count: %s;<br/>'
						'- failed fields: %s'
					) % (
								   self.name,
								   failed_count,
								   {'fields': '<br/>'.join(fields_preview) + more_text},
							   )
				}
			else:
				return {
					'message': _(
							'Report configuration successfully imported to: "%s"<br/>'
							'- Main fields: %s;<br/>'
							'- Detail fields: %s'
							) % (
								   self.name,
								   len(main_fields),
								   len(detail_fields),
							   )
				}

		except base64.binascii.Error:
			raise UserError(_('File format error: Unable to decode base64 data'))
		except json.JSONDecodeError as e:
			raise UserError(_('JSON format error:%s')% str(e))
		except Exception as e:
			raise UserError(_('Import failed: %s')% str(e))

	def _get_model_id_by_name(self, model_name):
		if not model_name:
			return False
		model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
		return model.id if model else False

	def _get_field_id_by_name(self, field_model, field_name):
		if not field_model or not field_name:
			return False
		field = self.env['ir.model.fields'].search([
			('model', '=', field_model),
			('name', '=', field_name)
		], limit=1)
		return field.id if field else False

	def write(self, vals):
		result = super().write(vals)

		if 'report_data' in vals:
			self._update_fonts_usage()

		return result

	def _update_fonts_usage(self):
		all_fonts = self.env['report.font'].search([])
		font_ids_to_update = []

		if self.report_data:
			try:
				import json
				report_config = json.loads(self.report_data)

				for font in all_fonts:
					if font._contains_font_in_config(report_config):
						font_ids_to_update.append(font.id)

				self.write({
					'used_font_ids': [(6, 0, font_ids_to_update)]
				})

				for font in all_fonts:
					reports_using_font = self.env['report.report'].search([
						('report_data', '!=', False),
						('id', '=', self.id)
					])

					found = False
					for report in reports_using_font:
						if report.report_data:
							try:
								config = json.loads(report.report_data)
								if font._contains_font_in_config(config):
									found = True
									break
							except:
								pass

					if found:
						if self.id not in font.used_in_report_ids.ids:
							font.write({
								'used_in_report_ids': [(4, self.id)]
							})
					else:
						if self.id in font.used_in_report_ids.ids:
							font.write({
								'used_in_report_ids': [(3, self.id)]
							})

			except Exception as e:
				pass

	@api.onchange('model_id', 'model_detail_id')
	def _onchange_models(self):
		if not self.model_id or not self.model_detail_id:
			return

		field = self.env['ir.model.fields'].search([
			('model', '=', self.model_detail_id.model),
			('ttype', '=', 'many2one'),
			('relation', '=', self.model_id.model)
		], limit=1)

		if field:
			self.model_main_key = field.name
		else:
			self.model_main_key = 'order_id'

	@api.depends('model_id')
	def _compute_available_detail_models(self):
		for rec in self:
			if not rec.model_id:
				rec.available_detail_model_ids = False
				continue

			fields = self.env['ir.model.fields'].search([
				('model_id', '=', rec.model_id.id),
				('ttype', '=', 'one2many')
			])

			relations = fields.mapped('relation')

			models = self.env['ir.model'].search([
				('model', 'in', relations)
			])

			rec.available_detail_model_ids = models

	@api.model
	def default_get(self, fields):
		res = super(ReportReport, self).default_get(fields)
		res['data_source'] = 'a' + ''.join(str(uuid.uuid4()).split('-'))
		return res

	def add_print_actions(self):
		self.ensure_one()
		# self.del_print_actions()

		if not self.group_field:
			raise UserError(_('Batch printing labels cannot be empty'))
		if not self.report_data:
			raise UserError(_('Please design the report content first'))

		if self.action_report_id:
			action_report_vals = {
				'name': self.name,
				'report_name': f'report.{self._table}.{self.id}',
				'model': self.model_id.model,
				'report_type': "tpstudio_r",
				'tpstudio_r_tag': "tpstudioR",
				'binding_model_id': self.model_id.id,
			}
			self.action_report_id.write(action_report_vals)
			action_report_record = self.action_report_id
		else:
			action_report_vals ={
				'name': self.name,
				"print_report_name": f"object.name + '-' + time.strftime('%Y%m%d')",
				'report_name': f'report.{self._table}.{self.id}',
				'model': self.model_id.model,
				"report_type": "tpstudio_r",
				"tpstudio_r_tag":"tpstudioR",
				"binding_model_id": self.model_id.id,
			}
			action_report_record = self.env['ir.actions.report'].create(action_report_vals)
		self.write({'display_completes': True,'action_report_id': action_report_record.id, })
		self._update_fonts_usage()

	def _format_time_field(self, field_value, field_type):
		if field_value == 'False':
			return ''
		if field_type in ['datetime']:
			if field_type == 'datetime':
				clean_str = str(field_value).split('.')[0][:19]
				return clean_str
		elif field_type in ['html']:
			if field_type == 'html':
				if field_value == 'False':
					return ''
				clean_str =  html2text.html2text(field_value)
				return clean_str
		elif field_type in ['boolean']:
			if field_value:
				re_str= "Yes"
			else:
				re_str= "No"
			return re_str
		else:
			return str(field_value)

	def _format_image_field(self, field_value, field_type):
		if field_type != 'binary':
			return field_value

		if not field_value:
			return ""

		if isinstance(field_value, bytes):
			image_base64 = field_value.decode('utf-8')
		else:
			image_base64 = field_value

		try:
			image_bytes = base64.b64decode(image_base64)

			img = Image.open(io.BytesIO(image_bytes))
			image_type = img.format.lower()

			data_url = f"data:image/{image_type};base64,{image_base64}"
			return data_url

		except Exception as e:
			return ""

	def unlink(self):
		for report in self:
			report.del_print_actions()

		return super(ReportReport, self).unlink()

	def cleanup_invalid_actions(self):
		report_models = self.env['report.report'].search([]).mapped('model_id.model')

		orphaned_actions = self.search([('model_id.model', 'not in', report_models)])


	def unlink_action_report(self):
		self.ensure_one()

		if self.action_report_id:
			self.action_report_id.write({
				'binding_model_id': False,
			})

			self.write({
				'display_completes': False,
			})

			return True

		return False

	def del_print_actions(self):
		self.ensure_one()
		if self.action_report_id:
			self.action_report_id.unlink()

		self.write({'display_completes': False, 'action_report_id': False})
		self.env.registry.clear_cache()

	def get_type(self, rmn):
		type_name=rmn.ttype
		field_value=rmn.field_value
		if field_value and 'n2c(' in field_value:
			type_name='char'
		res = {'char': 'string',
			   'text': 'string',
			   'one2many': 'string',
			   'many2one': 'string',
			   'many2many': 'string',
			   'integer': 'number',
			   'float': 'number',
			   'datetime': 'date',
			   'date': 'string',
			   'boolean': 'boolean',
			   'selection': 'string',
			   'monetary': 'number',
			   'binary': 'image',
			   'html': 'string',
			   'reference': 'string',
			   'image': 'image',
			   'image_url': 'string',
			   'json':'string'

			   }

		return res[type_name]

class ReportReportFun(models.AbstractModel):
	_name = "report.report.fun"
	_description = "Report Fun"

	def check_ean8(self, barcode):
		if len(barcode) != 8 or not barcode.isdigit():
			return ''

		prefix = barcode[:7]
		check_digit_input = int(barcode[7])

		total = 0
		for i, digit in enumerate(prefix):
			weight = 3 if i % 2 == 0 else 1
			total += int(digit) * weight

		check_digit_calculated = (10 - (total % 10)) % 10

		if check_digit_input == check_digit_calculated:
			return barcode
		else:
			return ''

	def check_upc(self, upc):
		if len(upc) != 12 or not upc.isdigit():
			return ''

		prefix = upc[:11]
		check_digit_input = int(upc[11])

		total = 0
		for i, digit in enumerate(prefix):
			weight = 3 if (i + 1) % 2 == 1 else 1
			total += int(digit) * weight

		check_digit_calculated = (10 - (total % 10)) % 10

		if check_digit_input == check_digit_calculated:
			return upc
		else:
			return ''

	def check_ean13(self, barcode):
		if len(barcode) != 13 or not barcode.isdigit():
			return ''

		prefix = barcode[:12]
		check_digit_input = int(barcode[12])

		total = 0
		for i, digit in enumerate(prefix):
			weight = 3 if (i + 1) % 2 == 0 else 1
			total += int(digit) * weight

		check_digit_calculated = (10 - (total % 10)) % 10

		if check_digit_input == check_digit_calculated:
			return barcode
		else:
			return ''

	def n_to_c(self, amount):
		if amount in (None, False, ''):
			return '零元整'

		try:
			amount = Decimal(str(amount))
		except (InvalidOperation, ValueError, TypeError):
			return '金额格式错误'
		if not amount:
			return '零元整'

		chinese_digits = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖']
		chinese_units = ['', '拾', '佰', '仟']
		chinese_big_units = ['', '万', '亿']

		# 处理整数部分
		int_part = int(amount)
		dec_part = round(amount - int_part, 2)  # 保留两位小数

		def convert_int(num):
			if num == 0:
				return '零'
			result = ''
			unit_index = 0
			while num > 0:
				section = num % 10000
				section_str = ''
				for i, digit in enumerate(str(section)[::-1]):
					digit = int(digit)
					if digit != 0:
						section_str = chinese_digits[digit] + chinese_units[i % 4] + section_str
					else:
						section_str = chinese_digits[digit] + section_str
				section_str = section_str.replace('零零', '零').strip('零')
				if section_str:
					result = section_str + chinese_big_units[unit_index] + result
				num = num // 10000
				unit_index += 1
			return result.replace('零零', '零').strip('零')

		def convert_dec(num):
			if num == 0:
				return '整'

			total_cents = round(num * 100)  # 总金额（分）
			jiao = total_cents // 10  # 角（十位）
			fen = total_cents % 10  # 分（个位）

			result = ''
			if jiao > 0:
				result += chinese_digits[jiao] + '角'
			if fen > 0:
				result += chinese_digits[fen] + '分'
			return result

		int_str = convert_int(int_part)
		dec_str = convert_dec(dec_part)

		return f"{int_str}元{dec_str}"

	def check_dec(self, product, description):
		if not product or not description:
			return description
		result = description
		result = re.sub(re.escape(product), '', result, flags=re.IGNORECASE)
		result = re.sub(r'\s+', ' ', result).strip()
		return result

	def print_null_row(self, row_n, list_len, index, set_n):
		page_count = (list_len + set_n - 1) // set_n
		index_in_page = (int(index) + set_n - 1) // set_n
		last_len = list_len - set_n * (page_count - 1)
		if page_count != index_in_page:
			return False
		else:
			if row_n - last_len > 0: return True
			return False

	def get_fun_list(self):
		c_f = {'check_ean8': self.check_ean8,
			   'check_upc': self.check_upc,
			   'check_ean13': self.check_ean13,
			   'n2c': self.n_to_c,
			   'check_dec': self.check_dec,
			   'pNr': self.print_null_row, }
		return c_f


