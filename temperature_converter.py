def fahrenheit_to_celsius(fahrenheit):
    return (fahrenheit - 32) / 1.8


def celsius_to_fahrenheit(celsius):
    return celsius * 1.8 + 32


def main():
    print("温度转换程序")
    print("1. 华氏温度转摄氏温度")
    print("2. 摄氏温度转华氏温度")

    choice = input("请选择转换方式（输入 1 或 2）：").strip()

    if choice == "1":
        fahrenheit = float(input("请输入华氏温度 F："))
        celsius = fahrenheit_to_celsius(fahrenheit)
        print(f"转换结果：{fahrenheit:.2f} 华氏度 = {celsius:.2f} 摄氏度")
    elif choice == "2":
        celsius = float(input("请输入摄氏温度 C："))
        fahrenheit = celsius_to_fahrenheit(celsius)
        print(f"转换结果：{celsius:.2f} 摄氏度 = {fahrenheit:.2f} 华氏度")
    else:
        print("输入无效，请重新运行程序并输入 1 或 2。")


if __name__ == "__main__":
    main()
