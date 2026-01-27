import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

enum ButtonType {
  primary,
  secondary,
  outline,
  text,
  icon,
}

enum ButtonSize {
  small,
  medium,
  large,
}

class CustomButton extends StatelessWidget {
  final String? text;
  final IconData? icon;
  final VoidCallback? onPressed;
  final ButtonType type;
  final ButtonSize size;
  final bool isLoading;
  final bool isDisabled;
  final Color? backgroundColor;
  final Color? textColor;
  final double? width;
  final double? height;
  final EdgeInsets? padding;
  final BorderRadius? borderRadius;

  const CustomButton({
    super.key,
    this.text,
    this.icon,
    this.onPressed,
    this.type = ButtonType.primary,
    this.size = ButtonSize.medium,
    this.isLoading = false,
    this.isDisabled = false,
    this.backgroundColor,
    this.textColor,
    this.width,
    this.height,
    this.padding,
    this.borderRadius,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isEnabled = onPressed != null && !isDisabled && !isLoading;
    
    // 尺寸配置
    double buttonHeight;
    EdgeInsets defaultPadding;
    double fontSize;
    
    switch (size) {
      case ButtonSize.small:
        buttonHeight = 32.h;
        defaultPadding = EdgeInsets.symmetric(horizontal: 16.w, vertical: 8.h);
        fontSize = 14.sp;
        break;
      case ButtonSize.medium:
        buttonHeight = 40.h;
        defaultPadding = EdgeInsets.symmetric(horizontal: 24.w, vertical: 12.h);
        fontSize = 16.sp;
        break;
      case ButtonSize.large:
        buttonHeight = 48.h;
        defaultPadding = EdgeInsets.symmetric(horizontal: 32.w, vertical: 16.h);
        fontSize = 18.sp;
        break;
    }

    // 颜色配置
    Color bgColor;
    Color fgColor;
    BorderSide? borderSide;

    switch (type) {
      case ButtonType.primary:
        bgColor = backgroundColor ?? theme.primaryColor;
        fgColor = textColor ?? Colors.white;
        break;
      case ButtonType.secondary:
        bgColor = backgroundColor ?? theme.colorScheme.secondary;
        fgColor = textColor ?? Colors.white;
        break;
      case ButtonType.outline:
        bgColor = Colors.transparent;
        fgColor = textColor ?? theme.primaryColor;
        borderSide = BorderSide(
          color: theme.primaryColor,
          width: 1.5,
        );
        break;
      case ButtonType.text:
        bgColor = Colors.transparent;
        fgColor = textColor ?? theme.primaryColor;
        break;
      case ButtonType.icon:
        bgColor = backgroundColor ?? Colors.transparent;
        fgColor = textColor ?? theme.primaryColor;
        break;
    }

    if (!isEnabled) {
      bgColor = bgColor.withOpacity(0.3);
      fgColor = fgColor.withOpacity(0.5);
    }

    Widget buttonChild;
    
    if (isLoading) {
      buttonChild = SizedBox(
        width: 20.w,
        height: 20.h,
        child: CircularProgressIndicator(
          strokeWidth: 2,
          valueColor: AlwaysStoppedAnimation<Color>(fgColor),
        ),
      );
    } else if (type == ButtonType.icon && icon != null) {
      buttonChild = Icon(
        icon,
        size: 24.sp,
        color: fgColor,
      );
    } else if (text != null) {
      buttonChild = Text(
        text!,
        style: TextStyle(
          color: fgColor,
          fontSize: fontSize,
          fontWeight: FontWeight.w500,
        ),
      );
    } else {
      buttonChild = const SizedBox.shrink();
    }

    return SizedBox(
      width: width,
      height: height ?? buttonHeight,
      child: Material(
        color: bgColor,
        borderRadius: borderRadius ?? BorderRadius.circular(8.r),
        child: InkWell(
          onTap: isEnabled ? onPressed : null,
          borderRadius: borderRadius ?? BorderRadius.circular(8.r),
          child: Container(
            padding: padding ?? defaultPadding,
            decoration: BoxDecoration(
              borderRadius: borderRadius ?? BorderRadius.circular(8.r),
              border: borderSide != null ? Border.fromBorderSide(borderSide) : null,
            ),
            child: Center(child: buttonChild),
          ),
        ),
      ),
    );
  }
}

// 预设按钮样式
class PrimaryButton extends CustomButton {
  const PrimaryButton({
    super.key,
    required String text,
    super.onPressed,
    super.size = ButtonSize.medium,
    super.isLoading = false,
    super.isDisabled = false,
    super.width,
  }) : super(text: text, type: ButtonType.primary);
}

class SecondaryButton extends CustomButton {
  const SecondaryButton({
    super.key,
    required String text,
    super.onPressed,
    super.size = ButtonSize.medium,
    super.isLoading = false,
    super.isDisabled = false,
    super.width,
  }) : super(text: text, type: ButtonType.secondary);
}

class OutlineButton extends CustomButton {
  const OutlineButton({
    super.key,
    required String text,
    super.onPressed,
    super.size = ButtonSize.medium,
    super.isLoading = false,
    super.isDisabled = false,
    super.width,
  }) : super(text: text, type: ButtonType.outline);
}

class TextButton extends CustomButton {
  const TextButton({
    super.key,
    required String text,
    super.onPressed,
    super.size = ButtonSize.medium,
    super.isLoading = false,
    super.isDisabled = false,
  }) : super(text: text, type: ButtonType.text);
}

class IconButton extends CustomButton {
  const IconButton({
    super.key,
    required IconData icon,
    super.onPressed,
    super.size = ButtonSize.medium,
    super.isLoading = false,
    super.isDisabled = false,
    super.backgroundColor,
    super.textColor,
  }) : super(icon: icon, type: ButtonType.icon);
}

