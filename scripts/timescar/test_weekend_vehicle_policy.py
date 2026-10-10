import json
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
import timescar_book_sat_3weeks as book
import timescar_extend_sun_3weeks as extend
from weekend_vehicle_policy import allowed_reservation, ordered_candidates


OPTIONS = [
    {'value': 's1', 'text': 'ベーシック／ソリオ'},
    {'value': 'r1', 'text': 'ベーシック／ライズ（ハイブリッド）（1）'},
    {'value': 'wrong', 'text': 'ベーシック／ヤリスクロス（ハイブリッド）'},
    {'value': 's2', 'text': 'ベーシック／ソリオ(ハイブリッド/1200cc)'},
    {'value': '1244976', 'text': 'ベーシック／ヤリスクロス（ハイブリッド）'},
    {'value': 'r2', 'text': 'ベーシック／ライズ（ハイブリッド）（2）'},
    {'value': 'gas', 'text': 'ベーシック／ライズ'},
    {'value': 'y', 'text': 'ベーシック／ヤリス（ハイブリッド）'},
]


def test_order_and_boundaries():
    assert [x['value'] for x in ordered_candidates(OPTIONS + OPTIONS)] == ['1244976', 'r1', 'r2', 's1', 's2']


@pytest.mark.parametrize('vehicle,identifier,expected', [
    ('ヤリスクロス', '', True), ('ライズ', 'ライズ（ハイブリッド）', True),
    ('ライズ', '', False), ('ライズ（ハイブリッド）', '', True),
    ('ソリオ', '', True), ('ソリオ(ハイブリッド/1200cc)', '', True),
    ('ヤリス（ハイブリッド）', '', False), ('MAZDA2', '', False),
])
def test_reservation_policy(vehicle, identifier, expected):
    assert allowed_reservation({'vehicle': vehicle, 'carIdentifier': identifier}) is expected


def test_candidate_fallback_stops_at_first_success(monkeypatch):
    candidates = ordered_candidates(OPTIONS)
    calls = []
    def prepare(page, candidate, start, end):
        calls.append(candidate['value'])
        return 'confirm' if candidate['value'] == 'r2' else None
    monkeypatch.setattr(book, 'prepare_candidate', prepare)
    runtime = SimpleNamespace(record_step=lambda **kw: None)
    assert book.prepare_first_available(None, candidates, None, None, runtime)['value'] == 'r2'
    assert calls == ['1244976', 'r1', 'r2']


def test_candidate_unknown_error_aborts(monkeypatch):
    calls = []
    def prepare(page, candidate, start, end):
        calls.append(candidate['value'])
        raise book.BookingError('unknown validation error')
    monkeypatch.setattr(book, 'prepare_candidate', prepare)
    with pytest.raises(book.BookingError, match='unknown'):
        book.prepare_first_available(None, ordered_candidates(OPTIONS), None, None, SimpleNamespace())
    assert calls == ['1244976']


def test_all_unavailable(monkeypatch):
    monkeypatch.setattr(book, 'prepare_candidate', lambda *args: None)
    with pytest.raises(book.BookingError, match='all allowed vehicles unavailable'):
        book.prepare_first_available(None, ordered_candidates(OPTIONS), None, None,
                                     SimpleNamespace(record_step=lambda **kw: None))


@pytest.mark.parametrize('body,unavailable', [
    ('入力内容に誤りがあります\n予約できない期間が含まれています', True),
    ('入力内容に誤りがあります\n別のエラー', False),
])
def test_form_error_never_submits(body, unavailable):
    clicked = []
    selected = {}
    page = SimpleNamespace(
        goto=lambda *a, **kw: None,
        select_option=lambda selector, *a, **kw: selected.update({selector: a or kw}),
        check=lambda selector: selected.update({selector: True}),
        wait_for_load_state=lambda *a: None,
        locator=lambda selector: SimpleNamespace(click=lambda: clicked.append(selector), inner_text=lambda: body),
    )
    start, end = book.target_window(datetime(2026, 10, 10, tzinfo=ZoneInfo('Asia/Tokyo')))
    if unavailable:
        assert book.prepare_candidate(page, ordered_candidates(OPTIONS)[0], start, end) is None
    else:
        with pytest.raises(book.BookingError, match='unrelated to availability'):
            book.prepare_candidate(page, ordered_candidates(OPTIONS)[0], start, end)
    assert clicked == ['#doCheck']
    assert selected['#exemptNocFlgYes'] is True


CONFIRM = '予約登録（確認）\n久我山４丁目２\nヤリスクロス（ハイブリッド） 1286 グレイッシュブルー\n利用開始日時\n2026年10月31日（土）09:00\n返却予定日時\n2026年10月31日（土）21:00'


@pytest.mark.parametrize('old,new', [('', ''), ('1286', '9999'), ('グレイッシュブルー', 'ホワイト'),
                                   ('09:00', '10:00'), ('21:00', '20:00'),
                                   ('ヤリスクロス', 'ライズ'), ('久我山４丁目２', '他の駅')])
def test_primary_confirmation(old, new):
    start, end = book.target_window(datetime(2026, 10, 10, tzinfo=ZoneInfo('Asia/Tokyo')))
    candidate = ordered_candidates(OPTIONS)[0]
    if old:
        with pytest.raises(book.BookingError):
            book.verify_candidate_confirmation(CONFIRM.replace(old, new), candidate, start, end)
    else:
        book.verify_candidate_confirmation(CONFIRM, candidate, start, end)


@pytest.mark.parametrize('vehicle', ['ライズ（ハイブリッド）', 'ソリオ', 'ソリオ(ハイブリッド/1200cc)'])
def test_fallback_duplicate_and_extension(monkeypatch, vehicle):
    saturday = datetime(2026, 10, 10, tzinfo=ZoneInfo('Asia/Tokyo'))
    start, end = book.target_window(saturday)
    reservation = {'station': book.TARGET_STATION, 'vehicle': vehicle,
                   'start': start.strftime('%Y-%m-%dT%H:%M'), 'return': end.strftime('%Y-%m-%dT%H:%M'),
                   'acceptedAt': '2026-10-10T00:15'}
    monkeypatch.setattr(book.subprocess, 'check_output', lambda *a, **kw: json.dumps({'reservations': [reservation]}))
    assert book.existing_reservation_for_target(saturday) == reservation
    monkeypatch.setattr(extend, 'fetch_reservations', lambda: [reservation])
    assert extend._select_target_reservation_with_reference(saturday.replace(day=11)) == reservation
