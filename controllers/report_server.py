import  uuid, json
import logging
import PIL.WebPImagePlugin
from odoo.tools.translate import _
from odoo import api, http,exceptions
from odoo.http import content_disposition, request
from urllib.parse import quote
import werkzeug.exceptions
from odoo.tools import html_escape
import re

_logger = logging.getLogger(__name__)
from werkzeug.urls import url_decode


def _get_headers(filetype, content, filename):
    header = [
        ("Content-Type", filetype),
        ("Content-Length", 1024),
        ("X-Content-Type-Options", "nosniff"),
    ]
    if filename:
        header.append(("Content-Disposition", content_disposition(filename)))
    return header

class ReportServer(http.Controller):

	@http.route('/tpstudio/report/report_server/run', type='http', auth='user', methods=['GET'],
				csrf=False, website=True, cors="*")
	def report_run(self, **kw):
		key = kw.get('key')
		output_format = kw.get('outputFormat')
		report = request.env['report.temp'].search([('p_key', '=', key)], limit=1)

		if not report:
			return request.make_response('Report not found', status=400)

		fname = kw.get('filename', 'report')
		if output_format == 'pdf':
			report_file = report.report_file_pdf
			headers = [
				('Content-Type', 'application/pdf'),
				('Access-Control-Allow-Origin', '*'),
				('Content-Disposition', f'inline; filename="{quote(fname)}.pdf"')
			]
		elif output_format == 'zip':
			report_file = report.report_file_xlsx
			headers = [
				('Content-Type', 'application/zip'),
				('Content-Disposition', f'inline; filename="{quote(fname)}.zip"')
			]
		else:
			report_file =  report.report_file_xlsx
			headers = [
				('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
				('Content-Disposition', f'inline; filename="{quote(fname)}.xlsx"')
			]

		return request.make_response(report_file, headers=headers)

	@api.model
	def handle_exception_error(self, e, reportname: str):
		_logger.exception("Error while generating report %s", reportname)
		se = http.serialize_exception(e)
		error = {"code": 200, "message": "Odoo Server Error", "data": se}
		res = request.make_response(html_escape(json.dumps(error)))
		raise werkzeug.exceptions.InternalServerError(response=res) from e

	@http.route(
		[
			"/report/<converter>/<reportname>",
			"/report/<converter>/<reportname>/<docids>",
		],
		type="http",
		auth="user",
		website=True,
		readonly=True,
	)
	def report_routes(self, reportname: str, docids: str | None = None, converter=None, **data):
		if converter != "tpstudio_r":
			return super().report_routes(reportname, docids, converter, **data)
		context = dict(request.env.context)
		context.update({"from_ir_report_controller": True})
		if data.get("options"):
			data.update(json.loads(data.pop("options")))
		if data.get("context"):
			context.update(json.loads(data["context"]))
		request.update_context(**context)

		tpstudio_r_report = request.env["ir.actions.report"]._get_report_from_name(reportname)

		report_content, file_name,content_type,_ = request.env["ir.actions.report"]._render_tpstudio(tpstudio_r_report, docids,data)

		if content_type == "pdf":
			filename = f"{file_name}.pdf"
			headers = _get_headers("application/pdf", report_content, filename)
		elif content_type == "zip":
			filename = f"{file_name}.zip"
			headers = _get_headers("zip", report_content, filename)
		elif content_type == "xlsx":
			filename = f"{file_name}.xlsx"
			headers = _get_headers("xlsx", report_content, filename)
		else:
			raise exceptions.UserError(_("Content type not supported."))
		return request.make_response(report_content, headers)

	def _call_tpstudio_r_converter(self, docids: str, reportname: str, context: str, url: "str"):
		if docids:
			response = self.report_routes(reportname, docids=docids, converter="tpstudio_r", context=context)
		else:

			data = dict(url_decode(url.split("?")[1]).items())  # decoding the args represented in JSON
			if "context" in data:
				context, data_context = json.loads(context or "{}"), json.loads(data.pop("context"))
				context = json.dumps({**context, **data_context})
			response = self.report_routes(reportname, converter="tpstudio_r", context=context, **data)
		return response

	@http.route(["/tpstudio_r/download"], type="http", auth="user")
	def report_download(self, data, context=None):
		requestcontent = json.loads(data)
		url, report_type = requestcontent[0], requestcontent[1]
		if report_type != "tpstudio_r":
			return super().report_download(data, context)
		reportname = url
		try:
			reportname = url.split("/report/tpstudio_r/")[1].split("?")[0]
			docids = None
			if "/" in reportname:
				reportname, docids = reportname.split("/")

			response = self._call_tpstudio_r_converter(docids, reportname, context, url)
			return response
		except Exception as e:
			self.handle_exception_error(e, reportname)

