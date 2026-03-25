/** @odoo-module */

import { _t } from "@web/core/l10n/translation";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { registry } from "@web/core/registry";
import { Component,onMounted,useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class PdfPrint extends Component {
    static template = "pdf.print";
    static props = {
        ...standardFieldProps,
        }
    setup(){
        this.pdfRef = useRef("pdf_preview");
        onMounted(() => {
            const url=this.props.record.context.url
            const url02=encodeURIComponent(url)
            const pdfjs_url=`/web/static/lib/pdfjs/web/viewer.html?file=${encodeURIComponent(url)}`
            if (this.usePdfJs()) {
                this.pdfRef.el.src = pdfjs_url;
                }
             else{
                this.pdfRef.el.src = url;
             }

//            this.setupIframeListener();
        })
    }
    setupIframeListener() {
        const iframeElement = this.pdfRef.el;

        if (!iframeElement) {
            return;
        }

        iframeElement.addEventListener('load', () => {
            setTimeout(() => {
                try {
                    if (iframeElement.contentWindow) {
                        iframeElement.contentWindow.print();
                    }
                } catch (error) {
                    console.error('Print failed:', error);

                }
            }, 1);
        });

        iframeElement.addEventListener('error', (e) => {
            console.error('Iframe load error:', e);
        });
    }
    usePdfJs() {

        const ua = navigator.userAgent;

        const isMobile =
            /Android|iPhone|iPad|iPod/i.test(ua);

        const isSafari =
            /^((?!chrome|android).)*safari/i.test(ua);

        const isIOS =
            /iPad|iPhone|iPod/.test(ua);

        if (isMobile || isSafari || isIOS) {
            return true;
        }
        return false;
    }
}
export const PdfPrintWidget = {
    component: PdfPrint,
    supportedTypes: ['html'],
    };
registry.category("fields").add("pdf_print", PdfPrintWidget);