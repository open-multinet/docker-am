FROM debian:jessie

RUN echo 'Acquire::ForceIPv4 "true";' | tee /etc/apt/apt.conf.d/99force-ipv4
RUN apt-get update && apt-get install -y openssh-server sudo
RUN mkdir /var/run/sshd

# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd

#Set sudo rights
RUN echo "ALL ALL=NOPASSWD: ALL\n" > /etc/sudoers.d/allow_everyone

#Set bash as default shell
RUN ln -sf /bin/bash /bin/sh

ENV NOTVISIBLE "in users profile"
RUN echo "export VISIBLE=now" >> /etc/profile

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]