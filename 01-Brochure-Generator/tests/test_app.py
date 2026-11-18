"""The Gradio app builds without an API key (catches mistakes in the UI wiring)."""

import gradio as gr

import app


def test_ui_builds():
    assert isinstance(app.build_ui(), gr.Blocks)


def test_reexport_does_nothing_before_a_brochure_exists():
    assert all(isinstance(value, type(gr.skip())) for value in app.reexport(None, "# Hi", "#1e3a8a"))
