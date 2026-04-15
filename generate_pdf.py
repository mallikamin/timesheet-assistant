from playwright.sync_api import sync_playwright
import os

def generate_pdf():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # Generate CFO Brief 1-Pager
        html_path = os.path.abspath('CFO-Brief-1-Pager.html')
        page.goto(f'file:///{html_path}')

        page.pdf(
            path='CFO-Brief-1-Pager.pdf',
            format='A4',
            margin={
                'top': '15mm',
                'right': '15mm',
                'bottom': '15mm',
                'left': '15mm'
            },
            print_background=True,
            display_header_footer=False
        )

        print("PDF generated successfully: CFO-Brief-1-Pager.pdf")

        browser.close()

if __name__ == '__main__':
    generate_pdf()
