import { fireEvent, render, screen } from '@testing-library/react';
import { AIDraft, Button, Input, StatusTag, TabBar } from './index';

test('button is at least touch size class and fires click', () => {
  const fn = vi.fn();
  render(<Button onClick={fn}>Save</Button>);
  fireEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(fn).toHaveBeenCalled();
});

test('status tag shows a word, not colour alone', () => {
  render(<StatusTag tone="alert">Overdue</StatusTag>);
  expect(screen.getByText('Overdue')).toBeTruthy();
});

test('input links its label and shows the error', () => {
  render(<Input label="Email" error="Required" />);
  expect(screen.getByLabelText('Email').getAttribute('aria-invalid')).toBe('true');
  expect(screen.getByText('Required')).toBeTruthy();
});

test('AI draft shows Draft until approved', () => {
  const { rerender } = render(<AIDraft title="Record">text</AIDraft>);
  expect(screen.getByText('Draft')).toBeTruthy();
  rerender(<AIDraft title="Record" approved>text</AIDraft>);
  expect(screen.queryByText('Draft')).toBeNull();
  expect(screen.getByText('Approved')).toBeTruthy();
});

test('tab bar marks the current tab', () => {
  const onChange = vi.fn();
  render(<TabBar tabs={[{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }]} active="a" onChange={onChange} />);
  expect(screen.getByText('A').getAttribute('aria-current')).toBe('page');
  fireEvent.click(screen.getByText('B'));
  expect(onChange).toHaveBeenCalledWith('b');
});
