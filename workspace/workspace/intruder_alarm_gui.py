import tkinter as tk
import winsound


def trigger_alarm():
    # Two-tone siren that can be triggered repeatedly without TTS issues.
    winsound.Beep(1200, 180)
    winsound.Beep(900, 180)
    winsound.Beep(1200, 180)


def main():
    root = tk.Tk()
    root.title('Intruder Alarm Control')
    root.geometry('320x180')

    label = tk.Label(root, text='Press the button to play the alarm.', font=('Segoe UI', 12))
    label.pack(pady=20)

    btn = tk.Button(root, text='Trigger Alarm', font=('Segoe UI', 14, 'bold'), bg='red', fg='white', command=trigger_alarm)
    btn.pack(pady=10, ipadx=10, ipady=8)

    root.mainloop()


if __name__ == '__main__':
    main()
