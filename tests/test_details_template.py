from pathlib import Path


def test_details_has_shared_responsive_top_button_row():
    template = (
        Path(__file__).parents[1] / "WSVINV" / "templates" / "details.html"
    ).read_text(encoding="utf-8")

    top_row = template.split('<div class="row">', 1)[0]
    assert "d-flex flex-wrap justify-content-between align-items-center gap-2 mb-4" in top_row
    assert '← Zurück zur Übersicht' in top_row
    assert 'class="btn btn-info text-white"' in top_row
    assert "url_for('export_docx', item_id=item.EquipmentID)" in top_row
    assert top_row.count("Export") == 1
    assert "{% if settings.docx_export.lower() == 'true' %}" in top_row
